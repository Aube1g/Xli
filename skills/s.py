 #!/usr/bin/env python3
"""
Собирает все README из скиллов по вебу и дизайну в одну папку.
"""
from pathlib import Path
import shutil

SKILLS_DIR = Path.home() / "v" / "skills"
OUTPUT_DIR = Path.home() / "v" / "web-design-readme"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ключевые слова для поиска скиллов по вебу и дизайну
WEB_DESIGN_KEYWORDS = [
    # Веб
    "landing-page", "responsive", "css", "react-component", "seo",
    "utm", "accessibility", "animation", "screenshot", "browser",
    "playwright", "youtube", "researching-web", "github-pages",
    "mkdocs", "cloudflare", "external-urls", "web", "html",
    "frontend", "website", "sitemap",

    # Дизайн
    "design-system", "color-palette", "font-pairing", "presentation-design",
    "design", "brand-consistency", "brand-voice", "color",
    "font", "logo", "icon", "svg", "ui", "ux",

    # Контент и скриншоты
    "screenshot-to-code", "stock-photo",
]

found = []
not_found = []

for skill_dir in sorted(SKILLS_DIR.iterdir()):
    if not skill_dir.is_dir() or skill_dir.name.startswith("."):
        continue

    # Проверяем, относится ли скилл к вебу/дизайну
    name_lower = skill_dir.name.lower()
    if not any(kw in name_lower for kw in WEB_DESIGN_KEYWORDS):
        continue

    # Ищем README (любой регистр и расширение)
    readme_candidates = list(skill_dir.glob("README*")) + \
                        list(skill_dir.glob("readme*")) + \
                        list(skill_dir.glob("Readme*")) + \
                        list(skill_dir.glob("*.md"))

    # Приоритет: README.md > SKILL.md > любой .md
    readme_file = None
    for pattern in ["README.md", "readme.md", "SKILL.md", "skill.md", "README", "readme"]:
        candidate = skill_dir / pattern
        if candidate.exists():
            readme_file = candidate
            break

    if not readme_file:
        # Берём первый попавшийся .md
        md_files = list(skill_dir.glob("*.md"))
        if md_files:
            readme_file = md_files[0]

    if readme_file and readme_file.exists():
        # Имя файла: skill-name--original-filename.md
        dest_name = f"{skill_dir.name}--{readme_file.name}"
        dest_path = OUTPUT_DIR / dest_name
        shutil.copy2(readme_file, dest_path)
        found.append((skill_dir.name, readme_file.name))
        print(f"  ✓ {skill_dir.name} → {dest_name}")
    else:
        not_found.append(skill_dir.name)
        print(f"  ✗ {skill_dir.name} — README не найден")

# ─── Создаём индексный файл ─────────────────
index_path = OUTPUT_DIR / "00-INDEX.md"
with open(index_path, "w", encoding="utf-8") as f:
    f.write("# 🌐 README скиллов по вебу и дизайну\n\n")
    f.write(f"**Всего найдено:** {len(found)}\n\n")
    f.write("| Скилл | Оригинальный файл |\n")
    f.write("|:---|:---|\n")
    for skill_name, orig_name in found:
        link = f"{skill_name}--{orig_name}"
        f.write(f"| `{skill_name}` | [{orig_name}]({link}) |\n")

    if not_found:
        f.write(f"\n## ⚠️ Без README ({len(not_found)})\n\n")
        for name in not_found:
            f.write(f"- `{name}`\n")

# ─── Итоги ─────────────────────────────────
print(f"\n{'─'*50}")
print(f"✅ Найдено и скопировано: {len(found)}")
print(f"❌ Без README: {len(not_found)}")
print(f"📁 Папка: {OUTPUT_DIR}")
print(f"📋 Индекс: {index_path}")
