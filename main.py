import json
import os
import sys
from loguru import logger
import warnings
import asyncio
import aiohttp
import itertools
from src import BiliUser

log = logger.bind(user="B站粉丝牌助手")
__VERSION__ = "0.4.4"

warnings.filterwarnings(
    "ignore",
    message="The localize method is no longer necessary, as this time zone supports the fold attribute",
)
os.chdir(os.path.dirname(os.path.abspath(__file__)).split(__file__)[0])

try:
    if os.environ.get("USERS"):
        users = json.loads(os.environ.get("USERS"))
    else:
        import yaml

        with open("users.yaml", "r", encoding="utf-8") as f:
            users = yaml.load(f, Loader=yaml.FullLoader)
    # 兼容旧版 users.yaml；新版本新增的配置项缺省时沿用文档建议值。
    users.setdefault("DOSIGN", 0)
    users.setdefault("DANMAKU_ONLY", 0)
    users.setdefault("WATCHINGLIVE", 30)
    users.setdefault("MIN_INTIMACY_THRESHOLD", 30)
    users.setdefault("WATCHINGLIVE_CD", 60)
    users.setdefault("LIKE_COUNT", 0)
    users.setdefault("DANMAKU_COUNT", 1)
    users.setdefault("DANMAKU_ROUND_ROBIN", 1)
    users.setdefault("WEARMEDAL", 0)
    users.setdefault("SIGNINGROUP_CD", 2)
    users.setdefault("CUSTOMSIGNIN_CD", 2)
    users.setdefault("CRON_INDEX", 0)
    assert users["DOSIGN"] in [0, 1], "DOSIGN参数错误"
    assert users["DANMAKU_ONLY"] in [0, 1], "DANMAKU_ONLY参数错误"
    assert users["WATCHINGLIVE"] >= 0, "WATCHINGLIVE参数错误"
    assert users["MIN_INTIMACY_THRESHOLD"] >= 0, "MIN_INTIMACY_THRESHOLD参数错误"
    assert users["WATCHINGLIVE_CD"] >= -1, "WATCHINGLIVE_CD参数错误"
    assert users["LIKE_CD"] >= -1, "LIKE_CD参数错误"
    assert users["LIKE_COUNT"] >= 0, "LIKE_COUNT参数错误"
    # assert users['SHARE_CD'] >= 0, "SHARE_CD参数错误"
    assert users["DANMAKU_CD"] >= -1, "DANMAKU_CD参数错误"
    assert users["DANMAKU_COUNT"] >= 0, "DANMAKU_COUNT参数错误"
    assert users["SIGNINGROUP_CD"] >= -1, "SIGNINGROUP_CD参数错误"
    assert users["CUSTOMSIGNIN_CD"] >= -1, "CUSTOMSIGNIN_CD参数错误"
    assert users["WEARMEDAL"] in [0, 1], "WEARMEDAL参数错误"
    assert users["DANMAKU_ROUND_ROBIN"] in [0, 1], "DANMAKU_ROUND_ROBIN参数错误"
    cron_index = users["CRON_INDEX"]
    assert isinstance(cron_index, int), "CRON_INDEX参数错误"
    config = {
        "DOSIGN": users["DOSIGN"],
        "DANMAKU_ONLY": users["DANMAKU_ONLY"],
        "WATCHINGLIVE": users["WATCHINGLIVE"],
        "MIN_INTIMACY_THRESHOLD": users["MIN_INTIMACY_THRESHOLD"],
        "WATCHINGLIVE_CD": users["WATCHINGLIVE_CD"],
        "LIKE_CD": users["LIKE_CD"],
        "LIKE_COUNT": users["LIKE_COUNT"],
        # "SHARE_CD": users['SHARE_CD'],
        "DANMAKU_CD": users["DANMAKU_CD"],
        "DANMAKU_COUNT": users["DANMAKU_COUNT"],
        "SIGNINGROUP_CD": users["SIGNINGROUP_CD"],
        "CUSTOMSIGNIN_CD": users["CUSTOMSIGNIN_CD"],
        "WEARMEDAL": users["WEARMEDAL"],
        "DANMAKU_ROUND_ROBIN": users["DANMAKU_ROUND_ROBIN"],
        "PROXY": users.get("PROXY"),
        "CRON_INDEX": cron_index,
        "TOTAL_CRON_COUNT": 0,
        "CURRENT_CRON_INDEX": 0,
        "STOPWATCHINGTIME": None,
    }
except Exception as e:
    log.error(f"读取配置文件失败，请检查配置文件格式是否正确：{e}")
    exit(1)


@log.catch
async def main():
    messageList = []
    test_mode = "--test" in sys.argv
    session = aiohttp.ClientSession(trust_env=True)
    try:
        resp = await (
            await session.get(
                "https://fansmedalhelper.02000721.xyz/version"
            )
        ).json()
        latest_version = resp["version"]
        need_update = latest_version != __VERSION__
        log.warning(f"当前版本：{__VERSION__}")
        log.warning(f"最新版本：{latest_version}，{'请更新' if need_update else '无需更新'}")
        if need_update:
            log.warning("更新内容：" + resp["changelog"])
            messageList.append(f"当前版本：{__VERSION__}")
            messageList.append(f"最新版本：{latest_version}，请更新")
            messageList.append(f"更新内容：{resp['changelog']} ")
        if resp["notice"]:
            log.warning("公告：" + resp["notice"])
            messageList.append(f"公告：{resp['notice']}")
    except Exception as ex:
        messageList.append(f"检查版本失败，{ex}")
        log.warning(f"检查版本失败，{ex}")
    initTasks = []
    startTasks = []
    catchMsg = []
    for user in users["USERS"]:
        if user["access_key"]:
            biliUser = BiliUser(
                user["access_key"],
                user.get("white_uid", ""),
                user.get("banned_uid", ""),
                config,
            )
            initTasks.append(biliUser.init(test_mode=test_mode))
            if not test_mode:
                startTasks.append(biliUser.start())
            catchMsg.append(biliUser.sendmsg())
    try:
        await asyncio.gather(*initTasks)
        if not test_mode:
            await asyncio.gather(*startTasks)
    except Exception as e:
        log.exception(e)
        # messageList = messageList + list(itertools.chain.from_iterable(await asyncio.gather(*catchMsg)))
        messageList.append(f"任务执行失败：{e}")
    finally:
        messageList = messageList + list(
            itertools.chain.from_iterable(await asyncio.gather(*catchMsg))
        )
    [log.info(message) for message in messageList]
    if users.get("SENDKEY", ""):
        await push_message(session, users["SENDKEY"], "  \n".join(messageList))
    await session.close()
    if users.get("MOREPUSH", ""):
        from onepush import notify

        notifier = users["MOREPUSH"]["notifier"]
        params = users["MOREPUSH"]["params"]
        await notify(
            notifier,
            title="【B站粉丝牌助手推送】",
            content="  \n".join(messageList),
            **params,
            proxy=config.get("PROXY"),
        )
        log.info(f"{notifier} 已推送")


def run(*args, **kwargs):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    cron_index = kwargs.get('cron_index', 0)
    total_count = kwargs.get('total_count', 0)
    config["CURRENT_CRON_INDEX"] = cron_index
    config["TOTAL_CRON_COUNT"] = total_count

    stoptime = users.get("STOPWATCHINGTIME")
    if stoptime:
        import time
        now = int(time.time())
        if isinstance(stoptime, int):
            delay = now + int(stoptime)
        else:
            delay = int(time.mktime(time.strptime(f'{time.strftime("%Y-%m-%d", time.localtime(now))} {stoptime}', "%Y-%m-%d %H:%M:%S")))
            delay = delay if delay > now else delay + 86400
        config["STOPWATCHINGTIME"] = delay
        log.info(f"本轮任务将在 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(delay))} 结束")
    else:
        config["STOPWATCHINGTIME"] = None

    loop.run_until_complete(main())
    log.info("任务结束，等待下一次执行。")


async def push_message(session, sendkey, message):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": "【B站粉丝牌助手推送】", "desp": message}
    await session.post(url, data=data)
    log.info("Server酱已推送")


if __name__ == "__main__":
    cron = users.get("CRON", None)

    if "--test" in sys.argv:
        log.info("测试模式：只执行登录和推送测试，跳过定时器与所有日常任务")
        run()
        log.info("测试任务结束")
    elif cron:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        schedulers = BlockingScheduler()
        
        # 处理多 cron 逻辑
        cron_list = []
        if isinstance(cron, list):
            # 如果 yaml 中写的是列表格式
            cron_list = cron
        elif isinstance(cron, str):
            # 如果是字符串，尝试用 '||' 分割（兼容环境变量写法）
            cron_list = cron.split('||')
        
        log.info(f"检测到定时配置，共 {len(cron_list)} 个任务")

        job_count = 0
        for index, cron_expr in enumerate(cron_list):
            cron_expr = cron_expr.strip()
            if not cron_expr:
                continue
            try:
                schedulers.add_job(run, CronTrigger.from_crontab(cron_expr),
                                   misfire_grace_time=3600,
                                   max_instances=1 if config['DANMAKU_ONLY'] else 2,
                                   kwargs={'cron_index': index + 1, 'total_count': len(cron_list)})
                log.info(f"已添加定时任务：[{cron_expr}] (第 {index + 1}/{len(cron_list)} 个)")
                job_count += 1
            except Exception as e:
                log.error(f"Cron 表达式 [{cron_expr}] 格式错误或添加失败：{e}")

        if job_count > 0:
            log.info("所有定时任务已启动，等待执行...")
            schedulers.start()
        else:
            log.error("未成功添加任何定时任务，请检查 CRON 配置")
            
    elif "--auto" in sys.argv:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import datetime

        log.info("使用自动守护模式，每隔 24 小时运行一次。")
        scheduler = BlockingScheduler(timezone="Asia/Shanghai")
        scheduler.add_job(
            run,
            IntervalTrigger(hours=24),
            next_run_time=datetime.datetime.now(),
            misfire_grace_time=3600,
            max_instances=2,
        )
        scheduler.start()
    else:
        log.info("未配置定时器，开启单次任务。")
        run()
        log.info("任务结束")
