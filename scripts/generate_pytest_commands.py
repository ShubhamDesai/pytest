import json
import os
import sys
import argparse
from pathlib import Path

def create_test_batch_json(test_list, output_dir, pr_id, batch_size=50):
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
    
    # Process test identifiers to ensure they're in the correct format
    processed_tests = []
    for test in test_list:
        # Remove any <Function ...> wrapper if present
        if test.strip().startswith("<Function ") and test.strip().endswith(">"):
            test = test.strip()[10:-1]
        processed_tests.append(test.strip())
    
    # Split tests into batches
    batches = []
    for i in range(0, len(processed_tests), batch_size):
        batches.append(processed_tests[i:i+batch_size])
    
    # Create JSON files for each batch
    batch_files = []
    for i, batch in enumerate(batches):
        batch_id = chr(97 + i % 26) * (1 + i // 26)  # a, b, c, ... z, aa, bb, etc.
        
        batch_data = {
            "batch_id": batch_id,
            "tests": batch,
            "command": {
                "executable": "pytest",
                "options": [
                    "--tb=short",
                    "--json-report",
                    f"--json-report-file=artifacts/pr-{pr_id}/test_results_batch_{batch_id}.json",
                    "-v"
                ],
                "test_identifiers": batch
            }
        }
        
        # Save to JSON file
        batch_file = output_path / f"batch_{batch_id}.json"
        with open(batch_file, 'w') as f:
            json.dump(batch_data, f, indent=2)
        
        batch_files.append(str(batch_file))
    
    # Create a manifest file listing all batches
    manifest = {
        "pr_id": pr_id,
        "batch_count": len(batches),
        "batch_files": batch_files,
        "total_tests": len(processed_tests)
    }
    
    with open(output_path / "manifest.json", 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return str(output_path / "manifest.json")

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
        
        cmd_parts = ["tox", "-e", tox_env, "--", batch['command']['executable']] + batch['command']['options']
        test_identifiers = " ".join(batch['command']['test_identifiers'])
        
        commands.append(f"echo 'Running batch {batch['batch_id']}...'")
        commands.append(f"{' '.join(cmd_parts)} {test_identifiers} || true")
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
    
    # Rest of your code...
    
    # Generate bash script with tox command
    if args.generate_script:
        bash_commands = generate_bash_commands(manifest_file, args.tox_env)
        script_path = Path(args.output_dir) / f"pr-{args.pr_id}" / f"run_{args.prefix}_tests.sh"
        
        with open(script_path, 'w') as f:
            f.write(bash_commands)
        
        # Make the script executable
        os.chmod(script_path, 0o755)
        print(f"Created bash script: {script_path}")

if __name__ == "__main__":
    main()
