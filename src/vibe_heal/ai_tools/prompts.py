"""Prompt templates for AI tools."""

from vibe_heal.sonarqube.models import SonarQubeIssue


def create_fix_prompt(issue: SonarQubeIssue, file_path: str) -> str:
    """Create a prompt for fixing a SonarQube issue.

    Args:
        issue: The SonarQube issue to fix
        file_path: Path to the file containing the issue

    Returns:
        Formatted prompt for AI tool
    """
    prompt = f"""Fix the following SonarQube issue in {file_path}:

**Issue Details:**
- Rule: {issue.rule}
- Severity: {issue.severity}
- Type: {issue.type}
- Line: {issue.line}
- Message: {issue.message}

**Instructions:**
1. Fix the issue while maintaining code functionality and style
2. Make minimal changes - only fix this specific issue
3. Do not fix other unrelated issues in the file
4. Ensure the fix doesn't break existing functionality
5. Follow the project's coding standards

Please make the necessary changes to fix this issue."""
    return prompt.strip()
