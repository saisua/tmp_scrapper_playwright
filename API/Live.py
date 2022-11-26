from logging import exception
from re import L
import cython
import asyncio
import traceback
from typing import *
from itertools import chain
from inspect import iscoroutinefunction
from multiprocessing import Process, Manager
from multiprocessing.managers import ListProxy

from API.Crawler import Crawler

class Live_slave(Crawler):
    slave_local_results:list
    
    def __init__(self, *args, **kwargs):
        self.slave_local_results = list()
        
        Crawler.__init__(self, *args, **kwargs)
    
    def exec_code(self, code):
        exec(code)

    def eval_code(self, code):
        print(eval(code))
    
    @staticmethod
    def slave_run(*args, slave_queue, slave_results, **kwargs):
        slave_process = Process(target=Live_slave._slave_target, args=[args, slave_queue, slave_results, kwargs])
        slave_process.start()

        return slave_process

    @staticmethod
    def _slave_target(args, slave_queue, slave_results, kwargs):
        slave = Live_slave(*args, **kwargs)

        loop = asyncio.get_event_loop()
        if(loop.is_running()):
            loop.stop()
            loop = asyncio.new_event_loop()

        loop.run_until_complete(slave._slave_run(slave_queue, slave_results))

    async def _slave_run(self, slave_queue, slave_results):
        print("Slave starting...")
        
        try:
            await self.open_crawler()

            print(f"Slave started ({len(slave_queue)})")

            while True:
                while(not len(slave_queue)):
                    print("[W]", end='\r')
                    await asyncio.sleep(3)
                
                func_name, mode, args, kwargs = slave_queue.pop(0)
                print(f"Slave got function \"{func_name}\"")
                if(func_name == "exit"):
                    break

                func = getattr(self, func_name)
                try:
                    if(iscoroutinefunction(func)):
                        print(f"Slave async {func_name}({args}, {kwargs})")
                        res = await func(*args, **kwargs)
                        try:
                            slave_results.append(res)
                        except TypeError:
                            self.slave_local_results.append(res)
                    else:
                        if(mode == "async"):
                            print(f"Slave async {func_name}({args}, {kwargs})")
                            res = await func(*args, **kwargs)
                            try:
                                slave_results.append(res)
                            except TypeError:
                                self.slave_local_results.append(res)
                        elif(mode == "agen"):
                            print(f"Slave agen {func_name}({args}, {kwargs})")
                            results = []
                            async for it in func(*args, **kwargs):
                                results.append(await it)
                            try:
                                slave_results.append(results)
                            except TypeError:
                                self.slave_local_results.append(results)
                        elif(mode == "gen"):
                            print(f"Slave gen {func_name}({args}, {kwargs})")
                            results = []
                            for it in func(*args, **kwargs):
                                results.append(it)
                            try:
                                slave_results.append(results)
                            except TypeError:
                                self.slave_local_results.append(results)
                        else:
                            print(f"Slave {func_name}({args}, {kwargs})")
                            res = func(*args, **kwargs)
                            try:
                                slave_results.append(res)
                            except TypeError:
                                self.slave_local_results.append(res)
                except Exception as err:
                    print(f"[-] {err}")
                    traceback.print_exception(err)
        except Exception as err:
            print(f"Exitted due to exception {err}")
        finally:
            await self.close_crawler()
        
class ProxyWrapper:
    attrs: list = []

    def __init__(self, attr=None):
        if(attr is not None):
            self.attrs.append(attr)

    def get(self) -> Any:
        attr = '.'.join(self.attrs)
        print(f"Get {attr}")

        prev_len = len(Live_browser.slave_shared_results)
        Live_browser.slave_shared_queue.append(("__getattr__", 0, [attr], {}))

        while(len(Live_browser.slave_shared_results) == prev_len):
            pass

        self.attrs.clear()
        return Live_browser.slave_shared_results[-1]

    def __getattr__(self, attr: str) -> object:
        self.attrs.append(attr)
        return self

    def __setattr__(self, attr: str, value: Any) -> None:
        attr = '.'.join(chain(self.attrs, [attr]))
        print(f"Set {attr} to {value}")
        Live_browser.slave_shared_queue.append(("__setattr__", 0, [attr, value], {}))
        self.attrs.clear()
        
    def __call__(self, *args, **kwargs):
        print(f"Added {'.'.join(self.attrs)} with ({args}, {kwargs})")
        
        mode = kwargs.pop('run_mode', '')
        Live_browser.slave_shared_queue.append(('.'.join(self.attrs), mode, args, kwargs))
        self.attrs.clear()
        
class Live_browser():
    slave_args: tuple
    slave_kwargs: dict

    slave_process: Process

    _manager: Manager
    
    slave_shared_queue: ListProxy
    slave_shared_results: ListProxy

    def __init__(self, *args, **kwargs):
        Live_browser._manager = Manager()
        Live_browser.slave_shared_queue = Live_browser._manager.list()
        Live_browser.slave_shared_results = Live_browser._manager.list()
        Live_browser.slave_args = args
        Live_browser.slave_kwargs = kwargs

    def __enter__(self, *args, **kwargs):
        Live_browser.slave_process = Live_slave.slave_run(
            *Live_browser.slave_args,
            slave_queue = Live_browser.slave_shared_queue,
            slave_results = Live_browser.slave_shared_results,
            **Live_browser.slave_kwargs
        )
        return self

    def __exit__(self, *args, **kwargs):
        Live_browser.slave_shared_queue.insert(0, ('exit', 0, 0, 0))
        Live_browser.slave_process.join()
        
    def __getattr__(self, attr):
        if(attr == 'wait'):
            return
        
        return ProxyWrapper(attr)

    def open(self):
        self.__enter__()

    def close(self):
        self.__exit__()