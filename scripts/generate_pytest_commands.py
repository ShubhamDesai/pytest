import json
import os
import sys
import argparse
from pathlib import Path

def create_test_batch_json(test_list, output_dir, pr_id, batch_size=20, prefix=''):
    """
    Create JSON files for test batches that can be used to generate pytest commands.
    
    Args:
        test_list: List of test identifiers
        output_dir: Directory to save JSON files
        pr_id: PR ID for naming the artifacts
        batch_size: Number of tests per batch
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir) / f"pr-{pr_id}"
    output_path.mkdir(parents=True, exist_ok=True)
    
    test_modules = {}
    for test in processed_tests:
        module = test.split("::")[0]
        if module not in test_modules:
            test_modules[module] = []
        test_modules[module].append(test)
    
    # Split tests into batches
    batches = []
    current_batch = []
    current_size = 0
    for module, tests in test_modules.items():
        if current_size + len(tests) > batch_size and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        current_batch.extend(tests)
        current_size += len(tests)
    if current_batch:
        batches.append(current_batch)
    
    # Create a manifest file listing all batches
    manifest = {
        "pr_id": pr_id,
        "batch_count": len(batches),
        "batch_files": batch_files,
        "total_tests": len(processed_tests),
        "prefix": prefix
    }
    
    manifest_file = output_path / f"{prefix}_manifest.json" if prefix else output_path / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return str(manifest_file)

def generate_bash_commands(manifest_file, tox_env):
    """
    Generate bash commands from the manifest file.
    
    Args:
        manifest_file: Path to the manifest JSON file
        tox_env: Tox environment to use
    
    Returns:
        A string containing bash commands
    """

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)
    
    commands = []
    commands.append("#!/bin/bash")
    commands.append(f"# Test commands for PR-{manifest['pr_id']}")
    commands.append(f"# Total batches: {manifest['batch_count']}")
    commands.append("")
    
    for batch_file in manifest['batch_files']:
        with open(batch_file, 'r') as f:
            batch = json.load(f)
        
        cmd_parts = ["tox", "-e", tox_env, "--"]
        options = " ".join(batch['command']['options'])
        
        # Properly escape each test identifier
        test_lines = []
        for test in batch['command']['test_identifiers']:
            # Double quote each test identifier and escape any internal quotes
            escaped_test = test.replace("'", "'\\''")
            test_lines.append(f"  '{escaped_test}'")
        

        test_str = " \\\n".join(test_lines)        
        commands.append(f"echo 'Running batch {batch['batch_id']}...'")
        commands.append(f"{' '.join(cmd_parts)} {options} {test_str} || true")
        commands.append("")
    
    return "\n".join(commands)

def main():
    parser = argparse.ArgumentParser(description='Generate JSON files for pytest commands')
    parser.add_argument('--input', '-i', required=True, help='Input file with test identifiers (one per line)')
    parser.add_argument('--output-dir', '-o', default='artifacts', help='Output directory for JSON files')
    parser.add_argument('--pr-id', '-p', required=True, help='PR ID for naming artifacts')
    parser.add_argument('--batch-size', '-b', type=int, default=50, help='Number of tests per batch')
    parser.add_argument('--generate-script', '-g', action='store_true', help='Generate bash script')
    parser.add_argument('--prefix', default='', help='Prefix for output files (e.g., "failed" for failed tests)')
    parser.add_argument('--tox-env', default='', help='Tox environment to use')
    
    args = parser.parse_args()
    
    # Read test identifiers from input file
    with open(args.input, 'r') as f:
        test_list = [line.strip() for line in f if line.strip()]
    
    # Create JSON files
    manifest_file = create_test_batch_json(
        test_list, 
        args.output_dir, 
        args.pr_id, 
        args.batch_size,
        args.prefix
    )
    
    print(f"Created manifest file: {manifest_file}")
    
    # Generate bash script if requested
    if args.generate_script:
        bash_commands = generate_bash_commands(manifest_file, args.tox_env)
        script_path = Path(args.output_dir) / f"pr-{args.pr_id}" / f"run_tests.sh"
        
        with open(script_path, 'w') as f:
            f.write(bash_commands)
        
        # Make the script executable
        os.chmod(script_path, 0o755)
        print(f"Created bash script: {script_path}")


if __name__ == "__main__":
    main()
