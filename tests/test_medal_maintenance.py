import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.user import BiliUser
from src import user as user_module


def medal(uid, *, live=0, lit=1):
    return {'medal': {'target_id': uid, 'medal_id': uid, 'is_lighted': lit},
            'room_info': {'room_id': uid, 'living_status': live},
            'anchor_info': {'nick_name': str(uid)}}


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def make_user(self, snapshots, *, limit=10, deadline=10000):
        clock = SimpleNamespace(now=100)
        api = SimpleNamespace(sendDanmaku=AsyncMock(), wearMedal=AsyncMock())
        api.snapshots = iter(snapshots)
        api.last = snapshots[-1]

        async def panel():
            api.last = next(api.snapshots, api.last)
            for row in api.last:
                yield row

        async def sleep(seconds):
            clock.now += max(seconds, 1)

        api.getFansMedalandRoomID = panel
        user = BiliUser.__new__(BiliUser)
        user.api = api
        user.name = 'test'
        user.medals = [medal(1), medal(2, lit=0)]
        user.message = []
        user.errmsg = []
        user.config = {'DANMAKU_COUNT': limit, 'DANMAKU_CD': 10, 'WEARMEDAL': 1,
                       'STOPWATCHINGTIME': deadline, 'DANMAKU_ONLY': 1}
        user.log = SimpleNamespace(info=lambda *a: None, debug=lambda *a: None,
                                   warning=lambda *a: None)
        fake_time = SimpleNamespace(time=lambda: clock.now, monotonic=lambda: clock.now)
        return user, fake_time, sleep

    async def test_lit_and_dark_medals_both_receive_ten_messages(self):
        user, timer, sleep = self.make_user([[medal(1), medal(2, lit=0)]])
        with patch.object(user_module, 'time', timer), patch.object(user_module.asyncio, 'sleep', sleep):
            await user.maintainMedalLights()
        rooms = [call.args[0] for call in user.api.sendDanmaku.await_args_list]
        self.assertEqual(rooms.count(1), 10)
        self.assertEqual(rooms.count(2), 10)

    async def test_live_room_waits_until_offline_and_is_not_sent_twice(self):
        user, timer, sleep = self.make_user([
            [medal(1, live=1)], [medal(1, live=1)], [medal(1)]
        ], limit=2)
        user.medals = [medal(1)]

        async def send(room):
            self.assertEqual(user.api.last[0]['room_info']['living_status'], 0)

        user.api.sendDanmaku.side_effect = send
        with patch.object(user_module, 'time', timer), patch.object(user_module.asyncio, 'sleep', sleep):
            await user.maintainMedalLights()
        self.assertEqual(user.api.sendDanmaku.await_count, 2)

    async def test_unknown_or_continuously_live_rooms_stop_before_next_day(self):
        user, timer, sleep = self.make_user([[medal(1, live=1)]], deadline=400)
        with patch.object(user_module, 'time', timer), patch.object(user_module.asyncio, 'sleep', sleep):
            await user.maintainMedalLights()
        user.api.sendDanmaku.assert_not_awaited()
        self.assertTrue(any('未补齐' in message for message in user.message))

    async def test_only_mode_skips_other_tasks_and_restores_medal(self):
        user, _, _ = self.make_user([[medal(1)]])
        user.isLogin = True
        user.maintainMedalLights = AsyncMock()
        user.restore_initial_medal = AsyncMock()
        user.like_v3 = AsyncMock()
        user.watchinglive = AsyncMock()
        user.signInGroups = AsyncMock()
        user.doCustomSignIn = AsyncMock()
        await user.start()
        user.maintainMedalLights.assert_awaited_once()
        user.restore_initial_medal.assert_awaited_once()
        for task in [user.like_v3, user.watchinglive, user.signInGroups, user.doCustomSignIn]:
            task.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
