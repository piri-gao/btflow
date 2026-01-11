.PHONY: install test backend frontend clean

# Install dependencies in editable mode
install:
	pip install -e .

# Run all tests
test:
	pytest tests/ -v

# Start Studio Backend
backend:
	@echo "🚀 Starting BTflow Studio Backend..."
	# Run module directly (requires btflow_studio package)
	export PYTHONPATH=$$PYTHONPATH:$$(pwd) && python -m btflow_studio.backend.app.main

# Start Studio Frontend
frontend:
	@echo "🎨 Starting BTflow Studio Frontend..."
	cd btflow_studio/frontend && npm run dev

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete

# Build Frontend Assets
build-frontend:
	@echo "📦 Building Studio Frontend..."
	cd btflow_studio/frontend && npm install && npm run build

# Build and Publish to PyPI
publish: build-frontend
	poetry build
	poetry publish
