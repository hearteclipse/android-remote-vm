# Contributing to VMI Platform

Thank you for your interest in contributing to the Virtual Mobile Infrastructure platform! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in Issues
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Docker version, etc.)
   - Logs and screenshots if applicable

### Suggesting Features

1. Check if the feature has been requested
2. Create an issue describing:
   - The problem it solves
   - Proposed solution
   - Alternative approaches considered
   - Impact on existing functionality

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Write/update tests
5. Update documentation
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/android-remote-vm.git
cd android-remote-vm

# Add upstream remote
git remote add upstream https://github.com/original/android-remote-vm.git

# Install dependencies
cd backend
pip install -r requirements.txt

# Run tests
pytest
```

## Coding Standards

### Python (Backend)

- Follow PEP 8
- Use type hints
- Write docstrings for functions/classes
- Maximum line length: 100 characters
- Use meaningful variable names

```python
# Good
def create_device(user_id: int, device_name: str) -> Device:
    """
    Create a new virtual Android device.
    
    Args:
        user_id: ID of the user creating the device
        device_name: Name for the new device
        
    Returns:
        Device: The created device object
    """
    pass

# Bad
def cd(u, n):
    pass
```

### JavaScript (Frontend)

- Use ES6+ features
- Use const/let instead of var
- Use async/await instead of callbacks
- Add JSDoc comments for functions

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and PRs

```
Add WebRTC reconnection logic

- Implement automatic reconnection on disconnect
- Add exponential backoff
- Update UI to show connection status

Fixes #123
```

## Testing

### Backend Tests

```bash
cd backend
pytest tests/
```

### Integration Tests

```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run tests
pytest tests/integration/
```

## Documentation

- Update README.md for new features
- Add docstrings to all functions/classes
- Update API documentation
- Include code examples

## Project Structure Guidelines

```
backend/
├── api/              # API endpoints (keep thin, delegate to services)
├── services/         # Business logic
├── models/           # Database models (if separated)
└── tests/            # Tests mirroring structure

client/
└── web/              # Web client files

android/              # Android container files
```

## Review Process

1. Automated checks must pass (linting, tests)
2. Code review by at least one maintainer
3. All feedback addressed
4. Documentation updated
5. No merge conflicts

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

Feel free to ask questions in:
- GitHub Issues
- Discussion forum
- Email maintainers

Thank you for contributing! 🎉

