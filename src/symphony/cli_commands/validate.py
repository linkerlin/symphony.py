"""Validate command for Symphony - Check configuration files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def validate_yaml_frontmatter(content: str) -> tuple[bool, list[str]]:
    """Validate YAML frontmatter syntax."""
    errors = []
    
    if not content.startswith("---"):
        errors.append("File must start with '---' for YAML frontmatter")
        return False, errors
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append("Invalid frontmatter format. Expected: ---\n<yaml>\n---\n<content>")
        return False, errors
    
    yaml_content = parts[1].strip()
    if not yaml_content:
        errors.append("YAML frontmatter is empty")
        return False, errors
    
    try:
        data = yaml.safe_load(yaml_content)
        if data is None:
            errors.append("YAML frontmatter parsed to None")
            return False, errors
        if "symphony" not in data:
            errors.append("Missing required 'symphony' key in frontmatter")
            return False, errors
    except yaml.YAMLError as e:
        errors.append(f"YAML parsing error: {e}")
        return False, errors
    
    return True, errors


def validate_symphony_config(config: dict) -> tuple[bool, list[dict]]:
    """Validate symphony configuration structure."""
    errors = []
    warnings = []
    
    symphony = config.get("symphony", {})
    
    # Check version
    version = symphony.get("version")
    if not version:
        errors.append({"type": "error", "message": "Missing 'symphony.version'"})
    elif version != "1.0":
        warnings.append({"type": "warning", "message": f"Unknown version: {version}"})
    
    # Check settings
    settings = symphony.get("settings", {})
    
    # LLM settings
    llm = settings.get("llm", {})
    provider = llm.get("provider", "openai")
    valid_providers = ["openai", "anthropic", "deepseek", "gemini", "azure"]
    if provider not in valid_providers:
        errors.append({
            "type": "error",
            "message": f"Invalid LLM provider: {provider}. Must be one of: {', '.join(valid_providers)}"
        })
    
    if not llm.get("model"):
        warnings.append({"type": "warning", "message": "LLM model not specified, will use default"})
    
    # Tracker settings
    tracker = settings.get("tracker", {})
    if tracker.get("kind") != "linear":
        errors.append({"type": "error", "message": "Only 'linear' tracker is currently supported"})
    
    if not tracker.get("project_slug"):
        errors.append({"type": "error", "message": "Missing 'tracker.project_slug'"})
    
    # Workspace settings
    workspace = settings.get("workspace", {})
    if not workspace.get("root"):
        warnings.append({"type": "warning", "message": "Workspace root not specified, will use default"})
    
    # Check prompt template
    prompt = symphony.get("prompt")
    if not prompt:
        warnings.append({"type": "warning", "message": "No custom prompt template defined, will use default"})
    
    return len(errors) == 0, errors + warnings


def validate_env_file(env_path: Path) -> tuple[bool, list[dict]]:
    """Validate environment file."""
    issues = []
    
    if not env_path.exists():
        issues.append({
            "type": "warning",
            "message": f"Environment file not found: {env_path}"
        })
        return True, issues  # Not a fatal error
    
    content = env_path.read_text()
    
    # Check for required variables based on detected provider
    required_vars = []
    
    # Detect which provider is being used
    if "OPENAI_API_KEY=" in content and not "OPENAI_API_KEY=\n" in content:
        if "OPENAI_API_KEY=your_" not in content and "OPENAI_API_KEY=$" not in content:
            required_vars.append("OPENAI_API_KEY")
    
    if "ANTHROPIC_API_KEY=" in content and "ANTHROPIC_API_KEY=\n" not in content:
        if "ANTHROPIC_API_KEY=your_" not in content:
            required_vars.append("ANTHROPIC_API_KEY")
    
    if "LINEAR_API_KEY=" in content and "LINEAR_API_KEY=\n" not in content:
        if "LINEAR_API_KEY=your_" not in content:
            required_vars.append("LINEAR_API_KEY")
    
    if "LINEAR_PROJECT_SLUG=" in content:
        if "LINEAR_PROJECT_SLUG=\n" in content or "LINEAR_PROJECT_SLUG=my-project" in content:
            issues.append({
                "type": "warning",
                "message": "LINEAR_PROJECT_SLUG appears to be using default value"
            })
    
    return len([i for i in issues if i["type"] == "error"]) == 0, issues


@click.command(name="validate")
@click.argument(
    "workflow_file",
    type=click.Path(exists=True, path_type=Path),
    default=Path("WORKFLOW.md"),
)
@click.option(
    "--env-file",
    "-e",
    type=click.Path(path_type=Path),
    help="Path to .env file",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors",
)
def validate_command(
    workflow_file: Path,
    env_file: Path | None,
    strict: bool,
) -> None:
    """Validate Symphony configuration files.
    
    Checks WORKFLOW.md syntax, structure, and environment configuration.
    """
    console.print(Panel.fit(
        f"[bold cyan]🔍 Validating Symphony Configuration[/bold cyan]\n"
        f"{workflow_file}",
        border_style="cyan"
    ))
    
    all_ok = True
    
    # Validate workflow file
    console.print(f"\n[bold]Checking {workflow_file.name}...[/bold]")
    
    content = workflow_file.read_text()
    
    # YAML frontmatter validation
    valid, errors = validate_yaml_frontmatter(content)
    if valid:
        console.print("  [green]✓[/green] YAML frontmatter syntax valid")
        
        # Parse and validate structure
        parts = content.split("---", 2)
        yaml_content = yaml.safe_load(parts[1])
        
        valid, issues = validate_symphony_config(yaml_content)
        
        for issue in issues:
            icon = "⚠" if issue["type"] == "warning" else "✗"
            color = "yellow" if issue["type"] == "warning" else "red"
            console.print(f"  [{color}]{icon}[/{color}] {issue['message']}")
            
            if issue["type"] == "error" or (strict and issue["type"] == "warning"):
                all_ok = False
        
        if valid and not issues:
            console.print("  [green]✓[/green] Configuration structure valid")
    else:
        for error in errors:
            console.print(f"  [red]✗[/red] {error}")
        all_ok = False
    
    # Validate environment file
    if env_file is None:
        env_file = workflow_file.parent / ".env"
    
    console.print(f"\n[bold]Checking {env_file.name}...[/bold]")
    
    valid, issues = validate_env_file(env_file)
    
    if env_file.exists():
        console.print(f"  [green]✓[/green] Environment file exists")
        
        for issue in issues:
            icon = "⚠" if issue["type"] == "warning" else "✗"
            color = "yellow" if issue["type"] == "warning" else "red"
            console.print(f"  [{color}]{icon}[/{color}] {issue['message']}")
            
            if issue["type"] == "error" or (strict and issue["type"] == "warning"):
                all_ok = False
        
        if valid and not issues:
            console.print("  [green]✓[/green] Environment configuration valid")
    else:
        console.print(f"  [yellow]⚠[/yellow] Environment file not found")
    
    # Summary
    console.print()
    if all_ok:
        console.print(Panel(
            "[bold green]✓ All checks passed![/bold green]",
            border_style="green"
        ))
        sys.exit(0)
    else:
        console.print(Panel(
            "[bold red]✗ Validation failed[/bold red]\n"
            "Please fix the errors above before running Symphony.",
            border_style="red"
        ))
        sys.exit(1)
