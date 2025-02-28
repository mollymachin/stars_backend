from azure.core.pipeline.policies import RetryPolicy
print("RetryPolicy methods:", [method for method in dir(RetryPolicy) if not method.startswith('_')])

# Let's see if we can create a RetryPolicy with custom backoff
try:
    from azure.core.pipeline.policies import RetryPolicy
    # Check if we can set retry settings without ExponentialBackoff
    policy = RetryPolicy()
    print("Successfully created RetryPolicy")
    print("RetryPolicy attributes:", vars(policy))
except Exception as e:
    print(f"Error creating RetryPolicy: {e}")
