import argparse
from library import fork_all
p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
fork_all(a.create)
