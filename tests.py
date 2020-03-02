import pytest
import uuid
import os
import app


@pytest.mark.asyncio
async def test_lst(monkeypatch):
    """The bot has to process the command /list|/lst"""
    db_path_test = f'{uuid.uuid4()}.sqlite'
    monkeypatch.setattr(app, 'DB_PATH', db_path_test)
    app.check_storage()

    async def query_ex_api_mock(path):
        return '{"rates":{"CAD":1.3443563815}}'

    monkeypatch.setattr(app, "query_ex_api", query_ex_api_mock)

    res = await app.handle_lst()
    assert 'CAD: 1.34' == res

    os.unlink(db_path_test)
