"""CLI principal do Data Hub."""
import typer
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(help="Data Hub CLI — Consulte seus dados via mensagem")
console = Console()


def run_async(coro):
    """Helper pra rodar async no CLI."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command()
def status():
    """Mostra status geral do Hub."""
    from src.core.hub import hub
    st = hub.status()

    table = Table(title="Data Hub Status")
    table.add_column("Componente", style="cyan")
    table.add_column("Qtd", style="green")
    table.add_row("Adapters (DBs)", str(st["adapter_count"]))
    table.add_row("Canais", str(st["channel_count"]))
    table.add_row("Regras", str(st["rule_count"]))

    console.print(table)
    if st["adapters"]:
        console.print(f"  DBs: {', '.join(st['adapters'])}")
    if st["channels"]:
        console.print(f"  Canais: {', '.join(st['channels'])}")
    if st["rules"]:
        console.print(f"  Regras: {', '.join(st['rules'])}")


@app.command()
def connections():
    """Lista conexões de database."""
    from src.core.hub import hub
    names = hub.adapters.list_names()

    if not names:
        console.print("[yellow]Nenhuma conexão registrada.[/yellow]")
        console.print("[dim]Use 'hub api' pra criar via API.[/dim]")
        return

    table = Table(title="Conexões de Database")
    table.add_column("Nome", style="cyan")
    table.add_column("Tipo", style="green")
    table.add_column("Config")

    for name in names:
        cfg = hub.adapters.get(name)
        db_type = cfg.get("db_type", cfg.get("_name", "?"))
        table.add_row(name, db_type, str({k: v for k, v in cfg.items() if not k.startswith("_")}))

    console.print(table)


@app.command()
def channels():
    """Lista canais de mensageria."""
    from src.core.hub import hub
    names = hub.channels.list_names()

    if not names:
        console.print("[yellow]Nenhum canal registrado.[/yellow]")
        return

    for name in names:
        cfg = hub.channels.get(name)
        console.print(f"  • [cyan]{name}[/cyan] ({cfg.get('channel_type', '?')})")


@app.command()
def rules():
    """Lista regras de intenção."""
    from src.core.hub import hub
    names = hub.rules.list_names()

    if not names:
        console.print("[yellow]Nenhuma regra registrada.[/yellow]")
        console.print("[dim]Crie regras via API POST /rules/[/dim]")
        return

    table = Table(title="Regras de Intenção")
    table.add_column("Nome", style="cyan")
    table.add_column("Método", style="green")
    table.add_column("Prioridade")
    table.add_column("Pattern/Desc")
    table.add_column("DB")

    for name in names:
        rule = hub.rules.get(name)
        method = "LLM" if rule.get("use_llm") else "Regex"
        pattern = rule.get("pattern", "") if not rule.get("use_llm") else rule.get("llm_description", "")[:50]
        table.add_row(
            name,
            method,
            str(rule.get("priority", 0)),
            pattern,
            rule.get("connection_name", "?"),
        )

    console.print(table)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Pergunta em linguagem natural"),
    connection: str = typer.Option(None, "--db", "-d", help="DB específico"),
):
    """Faz uma pergunta ao hub (Intent Engine)."""
    console.print(Panel(f"[bold]{question}[/bold]", title="Pergunta", border_style="blue"))

    from src.core.hub import hub
    from src.core.intent_engine import IntentEngine

    rules_data = list(hub.rules.list_all().values())
    engine = IntentEngine(rules=rules_data, llm_enabled=True)
    result = run_async(engine.process(question, target_connection=connection))

    if result.success and result.result:
        console.print(f"\n[green]✓ Método: {result.method} ({result.latency_ms:.0f}ms)[/green]")
        if result.query:
            console.print(f"[dim]Query: {result.query}[/dim]")
        console.print(f"\n{result.result.to_text()}")
    else:
        console.print(f"\n[red]✗ {result.error}[/red]")


@app.command()
def send(
    channel: str = typer.Argument(..., help="Canal (telegram/whatsapp)"),
    recipient: str = typer.Argument(..., help="Chat ID ou número"),
    message: str = typer.Argument(..., help="Mensagem a enviar"),
):
    """Envia mensagem via canal."""
    console.print(f"[bold]Enviando via {channel}...[/bold]")

    from src.core.hub import hub
    from src.channels.base import Message
    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel

    if not hub.channels.exists(channel):
        console.print(f"[red]Canal '{channel}' não registrado.[/red]")
        raise typer.Exit(1)

    config = hub.channels.get(channel)
    channel_type = config.get("channel_type", channel)
    channel_map = {"telegram": TelegramChannel, "whatsapp": WhatsAppChannel}
    cls = channel_map.get(channel_type)
    if not cls:
        console.print(f"[red]Tipo '{channel_type}' não suportado.[/red]")
        raise typer.Exit(1)

    instance = cls(config)
    msg = Message(recipient=recipient, content=message, channel=channel_type)
    sent = run_async(instance.send(msg))

    if sent:
        console.print("[green]✓ Mensagem enviada![/green]")
    else:
        console.print("[red]✗ Falha no envio.[/red]")


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", "--host", "-H"),
    port: int = typer.Option(8000, "--port", "-p"),
):
    """Inicia o servidor da API."""
    import uvicorn
    console.print(f"[bold green]Iniciando Data Hub API em http://{host}:{port}[/bold green]")
    console.print(f"[dim]Docs: http://{host}:{port}/docs[/dim]")
    uvicorn.run("src.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
