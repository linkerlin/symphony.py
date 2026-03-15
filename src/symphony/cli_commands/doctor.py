"""Symphony 的 doctor 命令 - 环境诊断。"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

console = Console()


async def check_llm_provider(provider: str, api_key: str | None, base_url: str | None) -> dict:
    """检查 LLM 提供商连接。"""
    result = {"name": provider, "status": "unknown", "message": ""}
    
    if not api_key:
        result["status"] = "not_configured"
        result["message"] = "API key not set"
        return result
    
    # 特定提供商的健康检查
    try:
        if provider == "openai":
            url = base_url or "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    result["status"] = "ok"
                    result["message"] = "Connected"
                elif response.status_code == 401:
                    result["status"] = "error"
                    result["message"] = "Invalid API key"
                else:
                    result["status"] = "warning"
                    result["message"] = f"HTTP {response.status_code}"
                    
        elif provider == "anthropic":
            url = base_url or "https://api.anthropic.com/v1/models"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    result["status"] = "ok"
                    result["message"] = "Connected"
                elif response.status_code == 401:
                    result["status"] = "error"
                    result["message"] = "Invalid API key"
                else:
                    result["status"] = "warning"
                    result["message"] = f"HTTP {response.status_code}"
                    
        elif provider == "deepseek":
            url = "https://api.deepseek.com/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    result["status"] = "ok"
                    result["message"] = "Connected"
                elif response.status_code == 401:
                    result["status"] = "error"
                    result["message"] = "Invalid API key"
                else:
                    result["status"] = "warning"
                    result["message"] = f"HTTP {response.status_code}"
                    
        elif provider == "gemini":
            # Gemini 使用不同的 API 结构
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    result["status"] = "ok"
                    result["message"] = "Connected"
                elif response.status_code == 400:
                    result["status"] = "error"
                    result["message"] = "Invalid API key"
                else:
                    result["status"] = "warning"
                    result["message"] = f"HTTP {response.status_code}"
        else:
            result["status"] = "unknown"
            result["message"] = f"Health check not implemented for {provider}"
            
    except httpx.TimeoutException:
        result["status"] = "warning"
        result["message"] = "Connection timeout"
    except httpx.ConnectError:
        result["status"] = "error"
        result["message"] = "Connection failed"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


async def check_linear(api_key: str | None) -> dict:
    """检查 Linear API 连接。"""
    result = {"name": "Linear", "status": "unknown", "message": ""}
    
    if not api_key:
        result["status"] = "not_configured"
        result["message"] = "API key not set"
        return result
    
    try:
        query = """
        query {
            viewer {
                id
                name
            }
        }
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                json={"query": query},
                headers={"Authorization": api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" not in data:
                    viewer = data.get("data", {}).get("viewer", {})
                    result["status"] = "ok"
                    result["message"] = f"Connected as {viewer.get('name', 'Unknown')}"
                else:
                    result["status"] = "error"
                    result["message"] = data["errors"][0].get("message", "GraphQL error")
            elif response.status_code == 401:
                result["status"] = "error"
                result["message"] = "Invalid API key"
            else:
                result["status"] = "warning"
                result["message"] = f"HTTP {response.status_code}"
                
    except httpx.TimeoutException:
        result["status"] = "warning"
        result["message"] = "Connection timeout"
    except httpx.ConnectError:
        result["status"] = "error"
        result["message"] = "Connection failed"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


def check_system_requirements() -> list[dict]:
    """检查系统要求。"""
    results = []
    
    # Python 版本
    py_version = sys.version_info
    if py_version >= (3, 12):
        results.append({
            "name": "Python Version",
            "status": "ok",
            "message": f"{py_version.major}.{py_version.minor}.{py_version.micro}"
        })
    else:
        results.append({
            "name": "Python Version",
            "status": "error",
            "message": f"{py_version.major}.{py_version.minor}.{py_version.micro} (requires 3.12+)"
        })
    
    # 磁盘空间
    try:
        stat = shutil.disk_usage(".")
        free_gb = stat.free / (1024**3)
        if free_gb > 1:
            results.append({
                "name": "Disk Space",
                "status": "ok",
                "message": f"{free_gb:.1f} GB free"
            })
        else:
            results.append({
                "name": "Disk Space",
                "status": "warning",
                "message": f"{free_gb:.1f} GB free (low)"
            })
    except Exception as e:
        results.append({
            "name": "Disk Space",
            "status": "warning",
            "message": str(e)
        })
    
    # 平台
    results.append({
        "name": "Platform",
        "status": "ok",
        "message": f"{platform.system()} {platform.machine()}"
    })
    
    return results


@click.command(name="doctor")
@click.option(
    "--env-file",
    "-e",
    type=click.Path(path_type=Path),
    help="Path to .env file",
)
def doctor_command(env_file: Path | None) -> None:
    """运行环境诊断。
    
    检查 LLM 提供商、Linear API 和系统要求的连接性。
    """
    console.print(Panel.fit(
        "[bold cyan]🏥 Symphony Environment Diagnostics[/bold cyan]",
        border_style="cyan"
    ))
    
    # 加载环境变量
    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    else:
        # 尝试从默认位置加载
        for env_path in [".env", ".env.local"]:
            if Path(env_path).exists():
                from dotenv import load_dotenv
                load_dotenv(env_path)
                break
    
    # 系统检查
    console.print("\n[bold]System Requirements[/bold]")
    system_results = check_system_requirements()
    for result in system_results:
        _print_result(result)
    
    # API 检查（异步）
    console.print("\n[bold]API Connectivity[/bold]")
    
    async def run_api_checks():
        checks = []
        
        # 检查所有配置的提供商
        providers = [
            ("openai", os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_BASE_URL")),
            ("anthropic", os.environ.get("ANTHROPIC_API_KEY"), os.environ.get("ANTHROPIC_BASE_URL")),
            ("deepseek", os.environ.get("DEEPSEEK_API_KEY"), None),
            ("gemini", os.environ.get("GEMINI_API_KEY"), None),
        ]
        
        for provider, key, base_url in providers:
            if key:  # 仅在密钥设置时检查
                result = await check_llm_provider(provider, key, base_url)
                checks.append(result)
        
        # Linear 检查
        linear_result = await check_linear(os.environ.get("LINEAR_API_KEY"))
        checks.append(linear_result)
        
        return checks
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Checking API connectivity...", total=None)
        api_results = asyncio.run(run_api_checks())
        progress.remove_task(task)
    
    for result in api_results:
        _print_result(result)
    
    # 摘要
    console.print()
    
    all_ok = all(r["status"] == "ok" for r in system_results + api_results)
    any_error = any(r["status"] == "error" for r in system_results + api_results)
    any_warning = any(r["status"] == "warning" for r in system_results + api_results)
    
    if all_ok:
        console.print(Panel(
            "[bold green]✓ All systems operational![/bold green]",
            border_style="green"
        ))
        sys.exit(0)
    elif any_error:
        console.print(Panel(
            "[bold red]✗ Some checks failed[/bold red]\n"
            "Please fix the errors above before running Symphony.",
            border_style="red"
        ))
        sys.exit(1)
    else:
        console.print(Panel(
            "[bold yellow]⚠ Some warnings detected[/bold yellow]\n"
            "Symphony may work, but review the warnings above.",
            border_style="yellow"
        ))
        sys.exit(0)


def _print_result(result: dict) -> None:
    """打印检查结果。"""
    status = result["status"]
    name = result["name"]
    message = result["message"]
    
    if status == "ok":
        icon = "[green]✓[/green]"
    elif status == "warning":
        icon = "[yellow]⚠[/yellow]"
    elif status == "error":
        icon = "[red]✗[/red]"
    elif status == "not_configured":
        icon = "[dim]○[/dim]"
    else:
        icon = "[dim]?[/dim]"
    
    console.print(f"  {icon} {name}: {message}")
