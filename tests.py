import pytest
import uuid
import os
import app
from aiogram.types.message import Message


@pytest.mark.asyncio
async def test_lst(monkeypatch):
    """The bot has to process the command /list|/lst"""
    with monkeypatch.context() as m:
        db_path_test = f'{uuid.uuid4()}.sqlite'
        m.setattr(app, 'DB_PATH', db_path_test)
        app.check_storage()

        async def query_ex_api_mock(path):
            return '{"rates":{"CAD":1.3443563815}}'

        m.setattr(app, "query_ex_api", query_ex_api_mock)

        res = await app.handle_lst()
    assert 'CAD: 1.34' == res

    os.unlink(db_path_test)


@pytest.mark.asyncio
async def test_lst_failure(monkeypatch):
    """The bot has to process the command /list|/lst with a notification about problems"""
    with monkeypatch.context() as m:
        db_path_test = f'{uuid.uuid4()}.sqlite'
        m.setattr(app, 'DB_PATH', db_path_test)
        app.check_storage()

        async def query_ex_api_err_mock(path):
            return '{"error":"Go away"}'

        m.setattr(app, "query_ex_api", query_ex_api_err_mock)

        res = await app.handle_lst()
    assert 'Exchange rate service is unavailable' == res

    os.unlink(db_path_test)


@pytest.mark.asyncio
async def test_exchange(monkeypatch):
    """The bot has to process the command /exchange"""
    with monkeypatch.context() as m:
        db_path_test = f'{uuid.uuid4()}.sqlite'
        m.setattr(app, 'DB_PATH', db_path_test)
        app.check_storage()

        async def query_ex_api_mock(path):
            return '{"rates":{"CAD":1.3443563815,"USD":1}}'

        m.setattr(app, "query_ex_api", query_ex_api_mock)

        res = await app.handle_exchange(Message(text='/exchange $10 to CAD'))
        assert '13.40 CAD' == res
        res = await app.handle_exchange(Message(text='/exchange 10 USD to CAD'))
        assert '13.40 CAD' == res
        res = await app.handle_exchange(Message(text='/exchange 10 RUB to CAD'))
        assert 'The command is wrong' == res
        # Use an unknown currency
        res = await app.handle_exchange(Message(text='/exchange 10 USD to XXX'))
        assert 'The command is wrong' == res
        res = await app.handle_exchange(Message(text='/exchange nothing'))
        assert 'The command is wrong' == res

    os.unlink(db_path_test)


@pytest.mark.asyncio
async def test_history(monkeypatch):
    """The bot has to process the command /history"""
    with monkeypatch.context() as m:
        chart = 0
        db_path_test = f'{uuid.uuid4()}.sqlite'
        m.setattr(app, 'DB_PATH', db_path_test)
        app.check_storage()

        async def query_ex_api_mock(path):
            if path.startswith('/latest'):
                return '{"rates":{"CAD":1.3443563815,"USD":1}}'
            else:
                return '{"rates":{"2020-02-26":{"CAD":1.3304827586},"2020-02-25":{"CAD":1.3286900369}}}'

        m.setattr(app, "query_ex_api", query_ex_api_mock)

        async def reply_photo_mock(self, f):
            nonlocal chart
            chart = 1

        m.setattr(Message, 'reply_photo', reply_photo_mock)

        await app.handle_history(Message(text='/history USD/CAD for 7 days'))
        assert chart == 1

    os.unlink(db_path_test)


@pytest.mark.asyncio
async def test_history_failure(monkeypatch):
    """The bot has to process the command /history with a notification about problems"""
    with monkeypatch.context() as m:
        message = 0
        db_path_test = f'{uuid.uuid4()}.sqlite'
        m.setattr(app, 'DB_PATH', db_path_test)
        app.check_storage()

        async def query_ex_api_mock(path):
            if path.startswith('/latest'):
                return '{"rates":{"CAD":1.3443563815,"USD":1}}'
            else:
                return '{"error":"Go away"}'

        m.setattr(app, "query_ex_api", query_ex_api_mock)

        async def answer_mock(self, m):
            nonlocal message
            message = m

        m.setattr(Message, 'answer', answer_mock)

        await app.handle_history(Message(text='/history USD CAD for 7 days'))
        assert message == 'The command is wrong'
        await app.handle_history(Message(text='/history USD/CAD for 7 days'))
        assert message == 'No exchange rate data is available for the selected currency.'

    os.unlink(db_path_test)
