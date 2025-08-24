import argparse, importlib, json, logging, os, time
from util.seen_store import SeenStore
from util.notifier import Notifier
from mattermostdriver import Driver

DEFAULT_CFG = "/etc/mattermost-newsfeeds/config.json"

def build_logger(level: str):
    lvl=getattr(logging, level.upper(), logging.DEBUG)
    logging.basicConfig(level=lvl, format='%(asctime)s %(levelname)s %(message)s')
    return logging.getLogger('mattermost-newsfeeds')

def load_sources(cfg, logger, seen, mattermost_api):
    general=cfg['general']
    out=[]
    for source_config in cfg.get('sources',[]):
        if not source_config.get('enabled',True): 
            continue
        notifier=Notifier(source_config.get('notifier_params',{}), mattermost_api, logger)
        mod=importlib.import_module(source_config['module'])
        cls=getattr(mod, source_config['class'])
        inst=cls(source_config.get('name', source_config['class']), source_config, general, seen, logger, notifier)
        inst.schedule_next()
        out.append(inst)
        logger.info(f"Loaded source: {source_config['name']} (poll {source_config.get('poll_seconds',300)}s)")
    return out

def find_config_path(cli_path: str):
    cwd_cfg=os.path.abspath(os.path.join(os.getcwd(),'config.json'))
    if os.path.exists(cwd_cfg): 
        return cwd_cfg
    return cli_path

def scheduler_loop(cfg, logger, mattermost_api):
    seen_path=cfg['general']['seen_store_path']
    if not os.path.isabs(seen_path):
        base_dir=os.path.abspath(os.path.join(os.path.dirname(__file__),'..'))
        seen_path=os.path.abspath(os.path.join(base_dir, seen_path))
    seen=SeenStore(seen_path, ttl_days=int(cfg['general'].get('seen_ttl_days',7)))
    seen.purge_old()

    sources=load_sources(cfg, logger, seen, mattermost_api)
    sleep_min=int(cfg['general'].get('sleep_min',1))
    sleep_max=int(cfg['general'].get('sleep_max',5))
    logger.info('Scheduler started.')
    while True:
        now=time.time(); ran=False
        for s in sources:
            if s.due():
                try: 
                    s.poll(now)
                except Exception as e: 
                    logger.exception(f"Error polling {s.name}: {e}")
                s.schedule_next()
                ran=True
        time.sleep(sleep_min if ran else sleep_max)
        seen.purge_old()

def main():
    ap=argparse.ArgumentParser(description='mattermost-newsfeeds')
    ap.add_argument('--config', default=DEFAULT_CFG, help=f"Path to config file (default: {DEFAULT_CFG})")
    args=ap.parse_args()
    cfg_path=find_config_path(args.config)
    try:
        with open(cfg_path,'r',encoding='utf-8') as f: 
            cfg=json.load(f)
    except Exception as e:
        print(f"Error loading config {cfg_path}: {e}")
        return
    logger=build_logger(cfg['general'].get('log_level','DEBUG'))
    general_cfg=cfg.get('general',{})
    login_cfg={
        'url': general_cfg['mattermost'].get('host',''),
        'token': general_cfg['mattermost'].get('token',''),
        'scheme': general_cfg['mattermost'].get('scheme','http'),
        'port': int(general_cfg['mattermost'].get('port',80)),
        'basepath': general_cfg['mattermost'].get('basepath','/api/v4').rstrip('/')
    }
    mattermost_api = Driver(login_cfg)
    mattermost_api.login()
    scheduler_loop(cfg, logger, mattermost_api)

if __name__=='__main__':
    main()
