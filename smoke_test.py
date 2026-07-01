import mintry

engine = mintry.init(
    api_key="dev_key",
    db_path="test_data/local.db",
)

engine.wallet.create_mandate("smoke_task", 100.00)
print(engine.wallet.get_mandate("smoke_task"))