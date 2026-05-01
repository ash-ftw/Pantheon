from __future__ import annotations

from sqlalchemy.orm import Session

from app.catalog import SCENARIOS, TEMPLATES
from app.models import AttackScenario, OrganizationTemplate, User
from app.security import hash_password


def seed_database(db: Session) -> None:
    for template in TEMPLATES:
        existing = db.get(OrganizationTemplate, template["id"])
        if not existing:
            db.add(
                OrganizationTemplate(
                    id=template["id"],
                    name=template["name"],
                    description=template["description"],
                    service_config_json={"services": template["services"]},
                    normal_traffic_json=template["normal_traffic"],
                )
            )
        else:
            existing.name = template["name"]
            existing.description = template["description"]
            existing.service_config_json = {"services": template["services"]}
            existing.normal_traffic_json = template["normal_traffic"]

    for scenario in SCENARIOS:
        existing = db.get(AttackScenario, scenario["id"])
        config = {
            "allowed_template_ids": scenario["allowed_template_ids"],
            "target_services": scenario["target_services"],
            "default_risk": scenario["default_risk"],
            "steps": scenario["steps"],
        }
        if not existing:
            db.add(
                AttackScenario(
                    id=scenario["id"],
                    scenario_name=scenario["scenario_name"],
                    description=scenario["description"],
                    difficulty=scenario["difficulty"],
                    attack_type=scenario["attack_type"],
                    scenario_config_json=config,
                )
            )
        else:
            existing.scenario_name = scenario["scenario_name"]
            existing.description = scenario["description"]
            existing.difficulty = scenario["difficulty"]
            existing.attack_type = scenario["attack_type"]
            existing.scenario_config_json = config

    if not db.query(User).filter(User.email == "demo@pantheon.local").first():
        db.add(
            User(
                name="Student Analyst",
                email="demo@pantheon.local",
                password_hash=hash_password("pantheon123"),
                role="Student",
            )
        )

    if not db.query(User).filter(User.email == "admin@pantheon.local").first():
        db.add(
            User(
                name="Platform Admin",
                email="admin@pantheon.local",
                password_hash=hash_password("admin123"),
                role="Admin",
            )
        )

    db.commit()
