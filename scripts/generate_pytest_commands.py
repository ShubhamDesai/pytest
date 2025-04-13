import json
import os
import sys
import glob
import argparse
from pathlib import Path

def combine_test_results(pr_id, workflow_id, output_dir="artifacts"):
    """
    Combine all batch test results into a single JSON file.
    
    Args:
        pr_id: PR ID for naming the artifacts
        workflow_id: Unique ID for the workflow in the matrix
        output_dir: Directory containing the artifacts
    """
    output_path = Path(output_dir) / f"pr-{pr_id}" / workflow_id
    
    # Find all batch result files
    batch_files = list(output_path.glob("test_results_batch_*.json"))
    
    if not batch_files:
        print(f"No batch result files found in {output_path}")
        return
    
    # Initialize combined results
    combined_results = {
        "created": None,
        "duration": 0,
        "exitcode": 0,
        "root": None,
        "environment": {},
        "summary": {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
            "error": 0,
            "total": 0
        },
        "tests": [],
        "collectors": [],
        "warnings": []
    }
    
    # Process each batch file
    for batch_file in batch_files:
        try:
            with open(batch_file, 'r') as f:
                batch_data = json.load(f)
            
            # Update summary
            for key in combined_results["summary"]:
                if key in batch_data["summary"]:
                    combined_results["summary"][key] += batch_data["summary"][key]
            
            # Add tests
            combined_results["tests"].extend(batch_data.get("tests", []))
            
            # Add collectors
            combined_results["collectors"].extend(batch_data.get("collectors", []))
            
            # Add warnings
            combined_results["warnings"].extend(batch_data.get("warnings", []))
            
            # Update duration
            combined_results["duration"] += batch_data.get("duration", 0)
            
            # Update exitcode (non-zero takes precedence)
            if batch_data.get("exitcode", 0) != 0:
                combined_results["exitcode"] = batch_data["exitcode"]
            
            # Use the first batch's created timestamp and root
            if combined_results["created"] is None and "created" in batch_data:
                combined_results["created"] = batch_data["created"]
            
            if combined_results["root"] is None and "root" in batch_data:
                combined_results["root"] = batch_data["root"]
            
            # Merge environment info
            combined_results["environment"].update(batch_data.get("environment", {}))
            
        except Exception as e:
            print(f"Error processing {batch_file}: {e}")
    
    # Save combined results
    combined_file = output_path / "test_results.json"
    with open(combined_file, 'w') as f:
        json.dump(combined_results, f, indent=2)
    
    print(f"Combined {len(batch_files)} batch results into {combined_file}")


def create_test_batch_json(test_list, output_dir, pr_id, workflow_id, batch_size=50, prefix=''):    
    """
    Create JSON files for test batches that can be used to generate pytest commands.
    
    Args:
        test_list: List of test identifiers
        output_dir: Directory to save JSON files
        pr_id: PR ID for naming the artifacts
        batch_size: Number of tests per batch
        prefix: Prefix for output files
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir) / f"pr-{pr_id}" / workflow_id
    output_path.mkdir(parents=True, exist_ok=True)

    # Process test identifiers to ensure they're in the correct format
    processed_tests = []
    for test in test_list:
        # Extract only the test identifier part (remove descriptions)
        test = test.strip()
        # If it contains a space, take only the part before the space
        if ' ' in test:
            test = test.split(' ')[0]
        # Remove any <Function ...> wrapper if present
        if test.startswith("<Function ") and test.endswith(">"):
            test = test[10:-1]
        # Only add if it looks like a valid test identifier
        if "::" in test or test.endswith(".py"):
            processed_tests.append(test)

    # Split tests into batches
    batches = []
    for i in range(0, len(processed_tests), batch_size):
        batches.append(processed_tests[i:i+batch_size])
    
    # Create JSON files for each batch
    batch_files = []
    for i, batch in enumerate(batches):
        batch_id = str(i + 1)  # 1, 2, 3, 4, etc.
        
        batch_data = {
            "batch_id": batch_id,
            "tests": batch,
            "command": {
                "executable": "pytest",
                "options": [
                    "--tb=short",
                    "--json-report",
                    f"--json-report-file=artifacts/pr-{pr_id}/{workflow_id}/test_results_batch_{batch_id}.json",
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
        "total_tests": len(processed_tests),
        "prefix": prefix
    }
    
    manifest_file = output_path / f"{prefix}_manifest.json" if prefix else output_path / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return str(manifest_file)

def generate_bash_commands(manifest_file, tox_env, workflow_id):
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
        
        # Create command with proper line breaks for readability
        commands.append(f"echo 'Running batch {batch['batch_id']}...'")
        commands.append(f"timeout 60s tox -e {tox_env} -- \\")
        commands.append("  --tb=short \\")
        commands.append("  --json-report \\")
        commands.append(f"  --json-report-file=artifacts/pr-{manifest['pr_id']}/test_results_batch_{batch['batch_id']}.json \\")
        commands.append("  -v \\")
        
        # Add test identifiers with proper escaping
        test_lines = []
        for test in batch['command']['test_identifiers']:
            # Escape any special characters in test names
            escaped_test = test.replace("'", "'\\''")
            test_lines.append(f"  '{escaped_test}'")
        
        # Join all test identifiers with line continuation
        test_str = " \\\n".join(test_lines)
        commands.append(test_str + " || true")
        commands.append("")
    
    # Add command to combine all batch results into a single file
    commands.append("# Combine all batch results into a single file")
    commands.append(f"python {os.path.abspath(__file__)} --combine-results --output-dir=artifacts --pr-id={manifest['pr_id']} --workflow-id={workflow_id}")
    commands.append("")
    
    return "\n".join(commands)

def main():
    parser = argparse.ArgumentParser(description='Generate JSON files for pytest commands')
    parser.add_argument('--input', '-i', required=True, help='Input file with test identifiers (one per line)')
    parser.add_argument('--output-dir', '-o', default='artifacts', help='Output directory for JSON files')
    parser.add_argument('--pr-id', '-p', required=True, help='PR ID for naming artifacts')
    parser.add_argument('--batch-size', '-b', type=int, default=20, help='Number of tests per batch')
    parser.add_argument('--generate-script', '-g', action='store_true', help='Generate bash script')
    parser.add_argument('--prefix', default='', help='Prefix for output files (e.g., "failed" for failed tests)')
    parser.add_argument('--tox-env', default='', help='Tox environment to use')
    parser.add_argument('--workflow-id', '-w', required=True, help='Unique ID for the workflow in the matrix')
    parser.add_argument('--combine-results', action='store_true', help='Combine batch results into a single file')

    args = parser.parse_args()

    if args.combine_results:
        combine_test_results(args.pr_id, args.workflow_id, args.output_dir)
        return
    
    if not args.input:
        parser.error("--input is required unless --combine-results is specified")
    
    # Read test identifiers from input file
    with open(args.input, 'r') as f:
        test_list = [line.strip() for line in f if line.strip()]
    
    # Create JSON files
    manifest_file = create_test_batch_json(
        test_list,
        args.output_dir,
        args.pr_id,
        args.workflow_id,
        args.batch_size,
        args.prefix
    )
    
    print(f"Created manifest file: {manifest_file}")
    
    # Generate bash script if requested
    if args.generate_script:
        bash_commands = generate_bash_commands(manifest_file, args.tox_env, args.workflow_id)
        script_path = Path(args.output_dir) / f"pr-{args.pr_id}" / args.workflow_id / f"run_{args.prefix}_tests.sh" if args.prefix else Path(args.output_dir) / f"pr-{args.pr_id}" / args.workflow_id / "run_tests.sh"
        with open(script_path, 'w') as f:
            f.write(bash_commands)
        
        # Make the script executable
        os.chmod(script_path, 0o755)
        print(f"Created bash script: {script_path}")

if __name__ == "__main__":
    main()
