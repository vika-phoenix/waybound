"""
analyze_code.py
Run from the backend folder:  python analyze_code.py

Uses Claude API to check your Django code for:
- Security vulnerabilities
- Performance / optimization issues
"""

import os
import time
import anthropic
from pathlib import Path
from decouple import config

# Load ANTHROPIC_API_KEY from .env into environment
os.environ.setdefault("ANTHROPIC_API_KEY", config("ANTHROPIC_API_KEY"))

# Files to analyze
FILES = [
    "apps/tours/views.py",
    "apps/users/views.py",
    "apps/bookings/views.py",
    "apps/reviews/views.py",
    "waybound/settings/base.py",
]

def read_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[File not found: {path}]"


def analyze(file_path: str, code: str) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from .env

    for attempt in range(4):
        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": f"""You are a Django security and performance expert.
Analyze this file: {file_path}

Look for:
1. Security vulnerabilities (auth bypass, injection, missing validation, exposed data)
2. Performance issues (N+1 queries, missing select_related, no pagination)
3. Quick optimization wins

Be concise. List only real issues found, with the line number and a one-line fix.
If no issues found, say "No issues found."

Code:
```python
{code}
```""",
                    }
                ],
            )
            return response.content[0].text

        except anthropic.OverloadedError:
            wait = 10 * (attempt + 1)
            print(f"  ⏳ API overloaded, retrying in {wait}s... (attempt {attempt+1}/4)")
            time.sleep(wait)

    return "  ❌ API still overloaded after retries. Try again in a few minutes."


def main():
    print("=" * 60)
    print("Claude Code Analyzer — Security & Optimization")
    print("=" * 60)

    for file_path in FILES:
        print(f"\n📄 Analyzing: {file_path}")
        print("-" * 40)
        code = read_file(file_path)
        if code.startswith("[File not found"):
            print(f"  ⚠️  {code}")
            continue
        result = analyze(file_path, code)
        print(result)

    print("\n" + "=" * 60)
    print("Analysis complete.")


if __name__ == "__main__":
    main()
