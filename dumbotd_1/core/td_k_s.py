from gevent import monkey
from dumbomvbastar.core.dumbomvba_star import smvbastar
monkey.patch_all(thread=False)
import collections

import hashlib
import multiprocessing
import pickle
from crypto.ecdsa.ecdsa import ecdsa_vrfy
from multiprocessing import Process
import copy
import logging
import os
import time
import gevent
from collections import defaultdict
from gevent import Greenlet
from gevent.queue import Queue
from dumbotd_1.core.nwabc import nwatomicbroadcast
from speedmvba.core.smvba_e_cp import speedmvba
from dumbobft.core.provablereliablebroadcast import decode
def set_consensus_log(id: int):
    logger = logging.getLogger("consensus-node-" + str(id))
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(filename)s [line:%(lineno)d] %(funcName)s %(levelname)s %(message)s ')
    if 'log' not in os.listdir(os.getcwd()):
        os.mkdir(os.getcwd() + '/log')
    full_path = os.path.realpath(os.getcwd()) + '/log/' + "consensus-node-" + str(id) + ".log"
    file_handler = logging.FileHandler(full_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
def hash(x):
    return hashlib.sha256(pickle.dumps(x)).digest()
class Dumbo_TD_k_s:
    def __init__(self, sid, pid, S, B, N, f, sPK, sSK, sPK2s, sSK2, send, recv, K=3, countpoint=0,mute=False,debug=False):
        self.sid = sid
        self.id = pid
        self.SLOTS_NUM = S 
        self.B = B
        self.N = N
        self.f = f
        self.sPK = sPK
        self.sSK = sSK
        self.sPK2s = sPK2s
        self.sSK2 = sSK2
        self._send = send
        self._recv = recv
        self.logger = set_consensus_log(pid)
        self.K = K
        self.transaction_buffer = [collections.deque() for _ in range(self.K)]
        self.output_list = [multiprocessing.Queue() for _ in range(N * self.K)]
        self.fast_recv = [multiprocessing.Queue() for _ in range(N * self.K)]
        self.mvba_recv = defaultdict(lambda: gevent.queue.Queue() )
        self.rc_recv = multiprocessing.Queue()
        self.debug = debug
        self.s_time = 0
        self.tx_cnt = 0
        self.total_tx = 0
        self.total_delay = 0
        self.count_delay = 0
        self.latency = 0
        self.a_latency = 0
        self.mute = mute
        self.threads = []
        self.txs = defaultdict(lambda: defaultdict())
        self.sigs = defaultdict(lambda: defaultdict(lambda: tuple()))
        self.sts = defaultdict(lambda: defaultdict())
        self.st_sum = 0
        self.current_tx = 0
        self.help_count = 0
        self.op = os.getpid()
        self.ap = 0
        self.countpoint = countpoint
        self.abc_count = 0
        self.vaba_latency = 0
        self.catch_up_sum = 0
        self.catch_up_sum1 = 0
        self.catch_up_sum2 = 0
        self.epoch = 0
        self.record_point = multiprocessing.Queue()
        self.record_point_out = multiprocessing.Queue()

    def submit_tx(self, tx, j):
        self.transaction_buffer[j].append(tx)
    def buffer_size(self, k):
        return len(self.transaction_buffer[k])
    def run_bft(self):
        self.s_time = time.time()
        if self.mute:
            muted_nodes = [each * 3 + 1 for each in range(int((self.N - 1) / 3))]
            if self.id in muted_nodes:
                while True:
                    time.sleep(10)
        for i in range(self.N * self.K):
            self.sigs[i][0] = ()
            self.txs[i][0] = "" 
        def _recv_loop():
            if os.getpid() != self.op:
                return
            print("run _recv_loop:", os.getpid())
            while True:
                try:
                    (sender, (r, msg)) = self._recv()
                    if msg[0] == 'STORED' or msg[0] == 'STORE' or msg[0] == 'PROPOSAL':
                        self.fast_recv[int(msg[1][6:])].put_nowait((sender, msg))
                    else:
                        if r == 'RCLOCK' or r == 'RCSTORE':
                            self.rc_recv.put_nowait((sender, msg))
                        else:
                            if r < self.epoch:
                                continue
                            self.mvba_recv[r].put_nowait((sender, msg[2]))
                except Exception as e:
                    continue
                gevent.sleep(0.001)
        def _finalize_output():
            sid = self.sid
            pid = self.id
            N = self.N
            K = self.K
            f = self.f
            prev_view = [0] * (N * K)
            cur_view = [0] * (N * K)
            recent_digest = defaultdict((lambda: defaultdict()))
            self.op = os.getpid()
    
            def _run_VABA_round(tx_to_send, send, recv):
                nonlocal sid, pid, N, K, f, prev_view, cur_view, recent_digest
                prev_view_e = copy.copy(prev_view)
                vaba_input = gevent.queue.Queue(1)
                vaba_output = gevent.queue.Queue(1)
                vaba_input.put_nowait(tx_to_send)

                sid_e = sid + ':' + str(self.epoch)
                self.tx_cnt = 0
                def make_vaba_predicate():
                    nonlocal sid, pid, N, K, f, prev_view_e, cur_view, recent_digest
                    def vaba_predicate(vj):
                        siglist = [tuple() for _ in range(N * K)]
                        (view, sigsdata, digestlist) = vj
                        siglist = pickle.loads(sigsdata)
                        cnt2 = 0
                        for i in range(N):
                            for j in range(K):
                                progress = view[i * K + j] - prev_view_e[i * K + j]
                                if progress == 0:
                                    continue
                                elif progress > 0:
                                    cnt2 += 1
                                    break
                                else:
                                    print("Wrong progress --- try rollback")
                                    return False
                        if cnt2 < N - f:
                            print("Wrong progress --- less than n-f")
                            return False
                        for i in range(N):
                            for j in range(K):
                                if view[i * K + j] <= cur_view[i * K + j]:
                                    try:
                                        assert self.txs[i * K + j][view[i * K + j]] == digestlist[i * K + j]
                                        return True
                                    except AssertionError as e:
                                        if self.logger is not None: self.logger.info(e)
                                        pass
                                    except KeyError as e:
                                        if self.logger is not None: self.logger.info(e)
                                        pass
                                if view[i * K + j] in recent_digest[i * K + j].keys():
                                    try:
                                        assert recent_digest[i * K + j][view[i * K + j]] == digestlist[i * K + j]
                                    except:
                                        print("inconsistent hash digest")
                                        return False
                                else:
                                    sid_r = sid + 'nw' + str(i * K + j)
                                    try:
                                        digest1 = hash(str(('STORED', sid_r, view[i * K + j], digestlist[i * K + j])))
                                        digest2 = digest1 + digest1
                                        for item in siglist[i * K + j]:
                                            (sender, sig_p) = item
                                            assert ecdsa_vrfy(self.sPK2s[sender], digest2, sig_p)
                                    except AssertionError:
                                        if self.logger is not None: self.logger.info("ecdsa signature failed!")
                                        print("ecdsa signature failed!")
                                        return False
                                    recent_digest[i * K + j][view[i * K + j]] = digestlist[i * K + j]
                        return True
                    return vaba_predicate
                if N >= 64:
                    vaba_thread_r = Greenlet(smvbastar, sid_e + 'VABA' + str(self.epoch), pid, N, f, self.sPK, self.sSK, self.sPK2s, self.sSK2,
                                            vaba_input.get, vaba_output.put_nowait, recv, send, predicate=make_vaba_predicate(), logger=self.logger)
                else:
                    vaba_thread_r = Greenlet(speedmvba, sid_e + 'VABA' + str(self.epoch), pid, N, f,
                                            self.sPK, self.sSK, self.sPK2s, self.sSK2,
                                            vaba_input.get, vaba_output.put_nowait,
                                            recv, send, predicate=make_vaba_predicate(), logger=self.logger)
                vaba_thread_r.start()
                out = vaba_output.get()
                (view, sig, txhash) = out
                self.current_tx = (sum(view) - sum(prev_view)) * self.B
                prev_view = view
            def _make_vaba_send(r):
                def _send(j, o):
                    self._send(j, (r, ('X_VABA', '', o)))
                return _send
            def track_progress():
                if os.getpid() != self.op:
                    return
                while True:
                    for i in range(self.N):
                        for j in range(self.K):
                            if self.output_list[i * self.K + j].qsize() > 1:
                                while self.output_list[i * self.K + j].qsize() > 2:
                                    for _ in range(self.output_list[i * self.K + j].qsize() - 2):
                                        self.output_list[i * self.K + j].get()
                                out = self.output_list[i * self.K + j].get()
                                (s, _, tx, sig, st) = out
                                if s > cur_view[i * self.K + j]:
                                    cur_view[i * self.K + j] = s
                                    self.txs[i * self.K + j][s] = tx
                                    self.sigs[i * self.K + j][s] = sig
                                    self.sts[i * self.K + j][s] = st
                                    if self.epoch > 100:
                                        del_p = max(0, cur_view[i * self.K + j] - 100)
                                        try:
                                            for p in list(self.txs[i * self.K + j]):
                                                if p < del_p:
                                                    self.txs[i * self.K + j].pop(p)
                                                    self.sigs[i * self.K + j].pop(p)
                                                    self.sts[i * self.K + j].pop(p)
                                            for p in list(recent_digest[i * K + j]):
                                                if p < del_p:
                                                    recent_digest[i * K + j].pop(p)
                                        except Exception as err:
                                            pass
                    gevent.sleep(0.01)
            gevent.spawn(track_progress)
            vaba_input = None
            if self.epoch == 0:
                if self.logger != None:
                    self.logger.info("*************************************************************")
                    self.logger.info("                         warm-up start                       ")
                    self.logger.info("*************************************************************")
            while True:
                if self.epoch == self.countpoint + 1:
                    zero = time.time()
                    if self.logger != None:
                        self.logger.info("warm-up time: %f" % (zero-self.s_time))
                        self.logger.info("*************************************************************")
                        self.logger.info("                       warm-up finished                      ")
                        self.logger.info("*************************************************************")
                send_r = _make_vaba_send(self.epoch)
                recv_r = self.mvba_recv[self.epoch].get
                while True:
                    count = [0 for _ in range(self.N)]
                    for i in range(self.N):
                        for j in range(self.K):
                            grow = cur_view[i * self.K + j] - prev_view[i * self.K + j]
                            if grow < 0:
                                count[i] = -1
                                break
                            elif grow > 0:
                                count[i] = 1
                        else:
                            continue
                        break
                    if sum(count) >= self.N - self.f and -1 not in count:
                        break
                    gevent.sleep(0)
                lview = copy.copy(cur_view) 
                sig_str = pickle.dumps([self.sigs[j][lview[j]] for j in range(int(self.N * self.K))])  
                vaba_input = (lview, sig_str, [self.txs[j][lview[j]] for j in range(self.N * self.K)])
                _run_VABA_round(vaba_input, send_r, recv_r)
                end = time.time()
                if self.epoch > self.countpoint:  
                    self.total_tx += self.current_tx  
                    self.count_delay = end - zero 

                    self.a_latency = self.count_delay /  (self.epoch - self.countpoint)

                if self.logger != None and self.epoch > self.countpoint:
                    self.logger.info("node: %d epoch: %d run: %f, "
                        "total delivered Txs after warm-up: %d, "
                        "average delay after warm-up: %f, "
                        " tps after warm-up: %f: "
                         %(self.id, self.epoch, self.count_delay, self.total_tx, self.a_latency, self.total_tx / self.count_delay))
                    print("node: %d epoch: %d run: %f, "
                        "total delivered Txs after warm-up: %d, "
                        "average delay after warm-up: %f, "
                        " tps after warm-up: %f:"
                        %(self.id, self.epoch, self.count_delay, self.total_tx, self.a_latency,self.total_tx / self.count_delay))
                if self.epoch > 2:
                    del self.mvba_recv[self.epoch - 3]
                self.epoch += 1
        self.s_time = time.time()
        if self.logger != None:
            self.logger.info('Node %d starts to run at time:' % self.id + str(self.s_time))
        def _make_send_nwabc():
            def _send(j, o):
                self._send(j, ('', o))
            return _send
        def abcs():
            self.ap = os.getpid()
            print("run n*k abcs:", os.getpid())
            for i in range(0, self.N):
                for j in range(self.K):
                    send = _make_send_nwabc()
                    recv = self.fast_recv[i * self.K + j].get
                    self._run_nwabc(send, recv, i, j)
            gevent.joinall(self.threads)
        self._abcs = Process(target=abcs)
        self._abcs.start()
        self._recv_output = gevent.spawn(_finalize_output)
        self._recv_thread = gevent.spawn(_recv_loop)
        self._abcs.join(timeout=86400)
    def _run_nwabc(self, send, recv, i, j):
        if os.getpid() == self.op:
            return 0
        sid = self.sid
        pid = self.id
        N = self.N
        f = self.f
        epoch_id = sid + 'nw'
        leader = i
        t = gevent.spawn(nwatomicbroadcast, epoch_id + str(i * self.K + j), pid, N, f, self.B, self.sPK2s, self.sSK2, leader,
                         self.transaction_buffer[j].popleft, self.output_list[i * self.K + j].put_nowait,recv, send, self.logger)
        self.threads.append(t)