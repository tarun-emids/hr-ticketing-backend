"""Service layer — business rules, no HTTP, no Supabase.

Services own the domain logic (lifecycle rules, notification emission,
draft submission, workload routing). They are constructed with repository
instances (and other services) rather than reaching for a global client,
which makes every rule unit-testable with in-memory fakes.
"""
