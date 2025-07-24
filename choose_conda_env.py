import os
import subprocess
import sys
import yaml
from pathlib import Path
import re

def parse_requirements(repo_path):
    # Check for environment.yml or requirements.txt
    env_file = Path(repo_path, "environment.yml")
    req_file = Path(repo_path, "requirements.txt")
    requirements = {}
    if env_file.exists():
        with open(env_file) as f:
            yml = yaml.safe_load(f)
            for dep in yml.get('dependencies', []):
                if isinstance(dep, str):
                    if '=' in dep:
                        pkg, _, ver = dep.partition('=')
                        requirements[pkg.strip()] = ver.strip()
                    else:
                        requirements[dep.strip()] = None
    elif req_file.exists():
        with open(req_file) as f:
            for line in f:
                if '==' in line:
                    pkg, ver = line.split('==')
                    requirements[pkg.strip()] = ver.strip()
                elif line.strip():
                    requirements[line.strip()] = None
    else:
        print("No environment.yml or requirements.txt found.")
        sys.exit(1)
    return requirements

def get_conda_envs():
    # List all conda environments
    result = subprocess.run(['conda', 'env', 'list'], capture_output=True, text=True)
    envs = []
    for line in result.stdout.splitlines():
        if line and not line.startswith('#') and '/' in line:
            env_name = line.split()[0]
            if env_name != 'base':  # Exclude the base environment here
                envs.append(env_name)
    return envs

def get_env_packages(env_name):
    # List installed packages for a given env
    result = subprocess.run(['conda', 'list', '-n', env_name], capture_output=True, text=True)
    pkgs = {}
    for line in result.stdout.splitlines():
        if line and not line.startswith('#') and len(line.split()) >= 2:
            pkg, ver = line.split()[0:2]
            pkgs[pkg] = ver
    return pkgs

def env_compatibility_score(env_pkgs, requirements):
    matches = 0
    conflicts = 0
    for pkg, req_ver in requirements.items():
        if pkg in env_pkgs:
            if req_ver is None or env_pkgs[pkg] == req_ver:
                matches += 1
            else:
                conflicts += 1
    return matches, conflicts

def update_claude_md(repo_path, env_name):
    # Insert or update a block in CLAUDE.md specifying environment
    claude_md = Path(repo_path) / "CLAUDE.md"
    env_section = f"\n# Python Environment\nClaude Code: Use the following Conda environment for this project:\nENV_NAME: {env_name}\n"
    if claude_md.exists():
        text = claude_md.read_text()
        if "ENV_NAME:" in text:
            text = re.sub(r'ENV_NAME: .*\n', f'ENV_NAME: {env_name}\n', text)
        else:
            text += env_section
        claude_md.write_text(text)
    else:
        claude_md.write_text(env_section)

def main(repo_path):
    requirements = parse_requirements(repo_path)
    envs = get_conda_envs()
    best_score = (-1, 999)  # (matches, conflicts)
    best_env = None

    # Find the existing env with most compatible packages and fewest conflicts
    for env in envs:
        env_pkgs = get_env_packages(env)
        matches, conflicts = env_compatibility_score(env_pkgs, requirements)
        if matches - conflicts > best_score[0] - best_score[1]:
            best_score = (matches, conflicts)
            best_env = env

    # Use existing env if compatibility is acceptable, else create a new one
    if best_score[0] >= max(1, len(requirements) // 2) and best_score[1] == 0:
        print(f"Using existing compatible Conda environment: {best_env}")
        chosen_env = best_env
    else:
        new_env = f"{Path(repo_path).name}_env"
        req_file = Path(repo_path, "environment.yml") if Path(repo_path, "environment.yml").exists() else Path(repo_path, "requirements.txt")
        print(f"Creating new conda environment: {new_env}")
        subprocess.run(['conda', 'create', '-n', new_env, '--file', str(req_file), '-y'])
        chosen_env = new_env

        # Clean-up: ask to keep/delete new env
        keep = input(f"Keep new environment '{new_env}'? (y/N): ").strip().lower()
        if keep != 'y':
            subprocess.run(['conda', 'remove', '-n', new_env, '--all', '-y'])
            print(f"Environment '{new_env}' deleted.")
            chosen_env = None

    if chosen_env:
        update_claude_md(repo_path, chosen_env)
        print(f"Updated CLAUDE.md with chosen environment: {chosen_env}")
        print(f"To run code: conda run -n {chosen_env} <your_command>")
    else:
        print("No environment available. Please rerun if needed.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python choose_conda_env.py <repo_path>")
        sys.exit(1)
    main(sys.argv[1])
