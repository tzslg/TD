import os
import gevent
import numpy as np
from coincurve import PrivateKey, PublicKey
from gevent import monkey, Greenlet;

from dumbotd_1.core.td_k_s import Dumbo_TD_k_s

monkey.patch_all(thread=False)

from typing import List, Callable
import pickle
from gevent import time, monkey
from myexperiements.sockettest.make_random_tx import tx_generator
from multiprocessing import Value as mpValue, Queue as mpQueue, Process

def load_key(id, N):
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sPK.key', 'rb') as fp:
        sPK = pickle.load(fp)
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sPK1.key', 'rb') as fp:
        sPK1 = pickle.load(fp)
    sPK2s = []
    for i in range(N):
        with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sPK2-' + str(i) + '.key', 'rb') as fp:
            sPK2s.append(PublicKey(pickle.load(fp)))
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'ePK.key', 'rb') as fp:
        ePK = pickle.load(fp)
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sSK-' + str(id) + '.key', 'rb') as fp:
        sSK = pickle.load(fp)
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sSK1-' + str(id) + '.key', 'rb') as fp:
        sSK1 = pickle.load(fp)
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'sSK2-' + str(id) + '.key', 'rb') as fp:
        sSK2 = PrivateKey(pickle.load(fp))
    with open(os.getcwd() + '/keys-' + str(N) + '/' + 'eSK-' + str(id) + '.key', 'rb') as fp:
        eSK = pickle.load(fp)
    return sPK, sPK1, sPK2s, ePK, sSK, sSK1, sSK2, eSK

class TDSNode_1(Dumbo_TD_k_s):
    def __init__(self, sid, id, S, Bfast, Bacs, N, f, 
                 bft_from_server: Callable, 
                 bft_to_client: Callable, 
                 ready: mpValue, 
                 stop: mpValue, 
                 mode='debug',
                 mute=False, tx_buffer=None, countpoint=0):
        self.sPK, self.sPK1, self.sPK2s, self.ePK, self.sSK, self.sSK1, self.sSK2, self.eSK = load_key(id, N)
        self.bft_from_server = bft_from_server
        self.bft_to_client   = bft_to_client
        self.ready = ready
        self.stop  = stop
        self.mode  = mode
        self.flag  = 0
        self.countpoint = countpoint
        if N == 4:
            K = 4
        elif N == 16:
            K = 2
        else:
            K = 1
        Dumbo_TD_k_s.__init__(self, sid, id, max(S, 10), max(int(Bfast), 1), N, f, 
                              self.sPK, self.sSK, self.sPK2s, self.sSK2,
                              send=None, recv=None, K=K, countpoint=countpoint, mute=mute)
        self.initial = [0] * self.K

    def client(self, k):
        if os.getpid() == self.op:
            return
        itr = 0
        rnd_tx = tx_generator(250)
        suffix = hex(self.id) + hex(k) + ">"
        for r in range(max(self.SLOTS_NUM, 1)):
            suffix1 = hex(r) + suffix
            tx_s = f'{rnd_tx[:-len(suffix1)]}{suffix1}'
            tx = [tx_s for _ in range(self.B)]
            Dumbo_TD_k_s.submit_tx(self, tx, k)
        self.initial[k] = 1
        while True:
            gevent.sleep(0.1)
            suffix1 = hex(itr) + suffix
            buffer_len = Dumbo_TD_k_s.buffer_size(self, k)
            if buffer_len < 10:
                for r in range(max(1, 1)):
                    suffix2 = hex(r) + suffix1
                    tx_s = f'{rnd_tx[:-len(suffix2)]}{suffix2}'
                    tx = [tx_s for _ in range(self.B)]
                    Dumbo_TD_k_s.submit_tx(self, tx, k)
            else:
                continue
            itr += 1

    def run(self):
        self._send = lambda j, o: self.bft_to_client((j, o))
        self._recv = lambda: self.bft_from_server()

        client_threads = [gevent.spawn(self.client, k) for k in range(self.K)]
        while sum(self.initial) == self.K:
            gevent.sleep(0.1)
        while not self.ready.value:
            time.sleep(0.1)

        self.run_bft()
        gevent.joinall(client_threads)
        self.stop.value = True