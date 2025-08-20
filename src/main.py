import argparse, importlib, json, logging, os, time
from util.seen_store import SeenStore
from util.notifier import Notifier

DEFAULT_CFG = "/etc/mattermost_newsfeeds/config.json"

def build_logger(level: str):
    lvl=getattr(logging, level.upper(), logging.DEBUG)
    logging.basicConfig(level=lvl, format='%(asctime)s %(levelname)s %(message)s')
    return logging.getLogger('mattermost_newsfeeds')

def load_sources(cfg, logger, seen, notifier):
    general=cfg['general']
    out=[]
    for s in cfg.get('sources',[]):
        if not s.get('enabled',True): 
            continue
        mod=importlib.import_module(s['module'])
        cls=getattr(mod, s['class'])
        inst=cls(s.get('name', s['class']), s, general, seen, logger, notifier)
        inst.schedule_next()
        out.append(inst)
        logger.info(f"Loaded source: {s['name']} (poll {s.get('poll_seconds',300)}s)")
    return out

def find_config_path(cli_path: str):
    cwd_cfg=os.path.abspath(os.path.join(os.getcwd(),'config.json'))
    if os.path.exists(cwd_cfg): 
        return cwd_cfg
    return cli_path

def scheduler_loop(cfg, logger):
    seen_path=cfg['general']['seen_store_path']
    if not os.path.isabs(seen_path):
        base_dir=os.path.abspath(os.path.join(os.path.dirname(__file__),'..'))
        seen_path=os.path.abspath(os.path.join(base_dir, seen_path))
    seen=SeenStore(seen_path, ttl_days=int(cfg['general'].get('seen_ttl_days',7)))
    seen.purge_old()
    notifier=Notifier(cfg['general'].get('notifier',{}))
    sources=load_sources(cfg, logger, seen, notifier)
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
    ap=argparse.ArgumentParser(description='mattermost_newsfeeds')
    ap.add_argument('--config', default=DEFAULT_CFG, help=f"Path to config file (default: {DEFAULT_CFG})")
    args=ap.parse_args()
    cfg_path=find_config_path(args.config)
    with open(cfg_path,'r',encoding='utf-8') as f: 
        cfg=json.load(f)
    logger=build_logger(cfg['general'].get('log_level','INFO'))
    scheduler_loop(cfg, logger)

if __name__=='__main__':
    main()
