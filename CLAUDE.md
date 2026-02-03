# CLAUDE.md - AI Assistant Guidelines for Main-Project

> **Repository Status**: This is a newly initialized repository. This document will be updated as the project structure develops.

## Project Overview

**Repository**: Main-Project
**Status**: Empty/Initial Setup
**Last Updated**: 2026-02-03

This document provides guidelines for AI assistants working with this codebase.

---

## Repository Structure

```
Main-Project/
├── .git/                 # Git version control
└── CLAUDE.md            # This file - AI assistant guidelines
```

*Structure will be updated as the project develops.*

---

## Technology Stack

*To be determined based on project requirements.*

---

## Development Workflow

### Branch Naming Convention

- Feature branches: `feature/<description>`
- Bug fixes: `fix/<description>`
- AI-assisted work: `claude/<session-id>`

### Commit Message Format

Follow conventional commits:
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

### Pull Request Guidelines

1. Create descriptive PR titles
2. Include a summary of changes
3. Reference related issues
4. Ensure all tests pass before requesting review

---

## Code Conventions

### General Principles

1. **Simplicity**: Prefer simple, readable code over clever solutions
2. **Consistency**: Follow existing patterns in the codebase
3. **Documentation**: Add comments only where logic isn't self-evident
4. **Testing**: Write tests for new functionality
5. **Security**: Never commit secrets, credentials, or sensitive data

### File Organization

- Keep related files together
- Use clear, descriptive file names
- Separate concerns appropriately

---

## Commands Reference

### Git Operations

```bash
# Check status
git status

# Create and switch to a new branch
git checkout -b <branch-name>

# Commit changes
git add <files>
git commit -m "<message>"

# Push to remote
git push -u origin <branch-name>
```

### Build & Test Commands

*To be added when build system is configured.*

---

## Important Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | AI assistant guidelines (this file) |

*Additional important files will be documented as the project develops.*

---

## API & External Services

*To be documented when integrations are added.*

---

## Known Issues & Limitations

*None currently documented.*

---

## AI Assistant Instructions

### When Working on This Repository

1. **Always read before editing**: Understand existing code before making changes
2. **Minimize changes**: Only modify what's necessary for the task
3. **Follow existing patterns**: Match the code style of the surrounding code
4. **Test your changes**: Run tests before committing
5. **Write clear commits**: Use descriptive commit messages
6. **Don't over-engineer**: Keep solutions simple and focused

### Things to Avoid

- Adding features not explicitly requested
- Creating unnecessary abstractions
- Committing debug code or console logs
- Making changes outside the scope of the task
- Guessing at missing requirements (ask instead)

### Security Considerations

- Never commit `.env` files or credentials
- Validate user input at system boundaries
- Be aware of OWASP Top 10 vulnerabilities
- Review changes for potential security issues

---

## Getting Started

### Prerequisites

*To be added based on technology stack.*

### Setup Instructions

*To be added once project is initialized.*

### Running the Project

*To be added once project is initialized.*

---

## Contact & Resources

*To be added.*

---

*This CLAUDE.md file should be updated whenever significant changes are made to the project structure, conventions, or workflows.*
