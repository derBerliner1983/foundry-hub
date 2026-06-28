"""Initialdaten: Einstellungen + Chef-Agent."""
from .config import config
from .models import Agent, Settings
from .roles import role_title


def ensure_seed(db):
    s = db.get(Settings, 1)
    if not s:
        s = Settings(
            id=1,
            autonomy_level="ask_for_hiring",
            allowed_providers="claude,openai,ollama",
            default_chef_provider=config.DEFAULT_CHEF_PROVIDER,
            default_chef_model=config.DEFAULT_CHEF_MODEL,
            default_worker_provider=config.DEFAULT_WORKER_PROVIDER,
            default_worker_model=config.DEFAULT_WORKER_MODEL,
            auto_run=config.AUTO_RUN_DEFAULT,
        )
        db.add(s)
        db.commit()

    chef = db.query(Agent).filter(Agent.role == "ceo").first()
    if not chef:
        chef = Agent(
            name="Carlo Chef",
            role="ceo",
            title=role_title("ceo"),
            provider=s.default_chef_provider,
            model=s.default_chef_model,
            status="employed",
            manager_id=None,
        )
        db.add(chef)
        db.commit()
    return chef
