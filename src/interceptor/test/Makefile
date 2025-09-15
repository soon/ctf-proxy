.PHONY: test-clean test-setup test-down clean test-docker

test: test-setup
	@echo "Running integration tests in Docker..."
	@docker-compose build test_runner
	@docker-compose run --rm test_runner
	@$(MAKE) test-down

test-setup:
	@echo "Building and starting test environment..."
	@docker-compose up -d --build --force-recreate
	@echo "Test environment started!"

test-down:
	@echo "Stopping test environment..."
	@docker-compose down -v

clean: test-down
	@echo "Cleaning up test artifacts..."
	@docker-compose down -v --rmi all 2>/dev/null || true
	@docker system prune -f

test-watch:
	@while true; do \
		$(MAKE) test-docker; \
		echo "Press Ctrl+C to stop, or any key to run again..."; \
		read -t 5 || continue; \
	done
