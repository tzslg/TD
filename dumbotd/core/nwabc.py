from gevent import monkey
from crypto.ecdsa.ecdsa import ecdsa_vrfy, ecdsa_sign
monkey.patch_all(thread=False)
import time
import gevent
from gevent.queue import Queue
import hashlib, pickle
from collections import defaultdict
from dumbobft.core.provablereliablebroadcast import encode
from honeybadgerbft.core.reliablebroadcast import merkleTree, getMerkleBranch, merkleVerify
stop = 0
def nwatomicbroadcast(sid, pid, N, f, Bsize, PK2s, SK2, leader, input, output, output2, receive, send, logger=None):
    """nw-abc
    :param sid: session id
    :param int pid: ``0 <= pid < N``
    :param int N:  at least 3
    :param int f: fault tolerance, ``N >= 3f + 1``
    :param PK2s: ``boldyreva.TBLSPublicKey`` with threshold n-f
    :param SK2: ``boldyreva.TBLSPrivateKey`` with threshold n-f
    :param int leader: ``0 <= leader < N``
    :param input: if ``pid == leader``, then :func:`input()` is called to wait for the input value
    :param receive: :func:`receive()` blocks until a message is received; 
        message is of the form::
            (i, (tag, ...)) = receive()
        where ``tag`` is one of ``{"VAL", "ECHO", "READY"}``
    :param send: sends (without blocking) a message to a designed
        recipient ``send(i, (tag, ...))``
    :return str: ``m`` after receiving :math:`2f+1` ``READY`` messages
        and :math:`N-2f` ``ECHO`` messages
        .. important:: **Messages**
            ``STORE( sid, s, tx[s], sigma[s-1])``
                snet from ``leader`` to all parties
            ``VOTE( sid, s, sig[s])``
                sent after receiving ``STORE`` message
    """

    assert N >= 3 * f + 1
    assert f >= 0
    assert 0 <= leader < N
    assert 0 <= pid < N
    SignThreshold = 2 * f + 1  
    s = 0
    Store = defaultdict()
    store = defaultdict(lambda: dict())
    K = N - 2 * f
    def hash(x):
        return hashlib.sha256(pickle.dumps(x)).digest()

    def broadcast(o):
        for i in range(N):
            send(i, o)

    if pid == leader:
        Store[s] = input()
        assert isinstance(Store[s], (str, bytes, list, tuple))
        stripes = encode(K, N, str(Store[s]).encode('utf-8'))
        mt = merkleTree(stripes)
        roothash = mt[1]
        for i in range(N):
            branch = getMerkleBranch(i, mt)
            send(i, ('STORE', sid, s, roothash, stripes[i], time.time(), branch))

    stored = defaultdict(set) 
    storedSigShares = defaultdict(lambda: dict())
    lock = defaultdict(lambda: dict())
    fixed_TX = defaultdict(dict)
    current_cert = [(0, None) for _ in range(N)]

    def handel_messages():
        nonlocal lock, sid, roothash, stripes, branch, store, stored, storedSigShares
        while True:
            sender, msg = receive(timeout=1000)
            if msg[0] == 'STORE':
                (_, sid_r, r, roothash_r, stripe_r, st, branch_r) = msg
                if sender != leader:
                    if logger is not None:
                        logger.info("STORE message from other than leader: %d" % sender)
                    continue
                try:
                    assert merkleVerify(N, stripe_r, roothash_r, branch_r, pid)
                except Exception as e:
                    continue
                store[r][sender] = msg
                if r == 0:
                    digest1 = hash(str(('STORED', sid_r, roothash_r)))
                    digest2 = digest1 + digest1
                    sigsh = ecdsa_sign(SK2, digest2)
                    send(leader, ('STORED', sid_r, r, sigsh, roothash_r))
                    fixed_TX[r][sender] = (r, stripe_r, roothash_r, branch_r, 0)
                    del store[r][sender]
                    output2(fixed_TX[r][sender])
                    del fixed_TX[r][sender]

                    continue
                try:
                    if lock[r - 1][sender]:
                        digest1 = hash(str(('STORED', sid_r, roothash_r)))
                        digest2 = digest1 + digest1
                        sigsh = ecdsa_sign(SK2, digest2)
                        send(leader, ('STORED', sid_r, r, sigsh, roothash_r))
                        fixed_TX[r][sender] = (r, stripe_r, roothash_r, branch_r, lock[r - 1][sender])
                        del store[r][sender]
                        output2(fixed_TX[r][sender])
                        del fixed_TX[r][sender]
                except:
                    gevent.sleep(0)
                
            if msg[0] == 'STORED':
                (_, sid_r, r, rec_sigsh, roothash_r) = msg
                if pid != leader:
                    continue
                try:
                    digest1 = hash(str(('STORED', sid_r, roothash_r)))
                    digest2 = digest1 + digest1
                    assert ecdsa_vrfy(PK2s[sender], digest2, rec_sigsh)
                except AssertionError:
                    continue
                stored[roothash_r].add(sender)
                storedSigShares[r][sender] = rec_sigsh 
                if len(stored[roothash_r]) == SignThreshold:
                    Sigma1 = tuple(storedSigShares[r].items())
                    broadcast(('PROPOSAL', sid_r, r, roothash_r, time.time(), Sigma1))
                    del storedSigShares[r]                     
                    del stored[roothash_r]
                    r2 = r + 1
                    while True:
                        try:
                            Store[r2] = input()
                            break
                        except:
                            gevent.sleep(0)
                    assert isinstance(Store[r2], (str, bytes, list, tuple))
                    stripes = encode(K, N, str(Store[r2]).encode('utf-8'))
                    mt = merkleTree(stripes)
                    roothash = mt[1]
                    for i in range(N):
                        branch = getMerkleBranch(i, mt)
                        send(i, ('STORE', sid, r2, roothash, stripes[i], time.time(), branch))
                    if r2 > 20:
                        del Store[r2-20]
                   
            if msg[0] == 'PROPOSAL':
                (_, sid_r, r, roothash_r, st, rec_sig) = msg
                try:
                    digest1 = hash(str(('STORED', sid_r, roothash_r)))
                    digest2 = digest1 + digest1
                    for item in rec_sig:
                        (sender2, sig_p) = item
                        assert ecdsa_vrfy(PK2s[sender2], digest2, sig_p)
                    lock[r][sender] = rec_sig
                except AssertionError:
                    if logger is not None: logger.info("ecdsa signature failed!")
                    continue
                try:
                    if store[r+1][sender]:
                        (_, sid_r, r2, roothash_r, stripe_r, st, branch_r) = store[r+1][sender]
                        digest1 = hash(str(('STORED', sid_r, roothash_r)))
                        digest2 = digest1 + digest1
                        sigsh = ecdsa_sign(SK2, digest2)
                        send(leader, ('STORED', sid_r, r2, sigsh, roothash_r))
                        del store[r2][sender]
                        fixed_TX[r2][sender] = (r2, stripe_r, roothash_r, branch_r, rec_sig)
                        output2(fixed_TX[r2][sender])
                        del fixed_TX[r2][sender]
                except:
                    pass
                if r > current_cert[sender][0]:
                    current_cert[sender] = (r, sid_r, roothash_r, rec_sig, st)
                    output(current_cert[sender])
                if r > 20:
                    del lock[r-20]
            gevent.sleep(0)
    recv_thread = gevent.spawn(handel_messages)
    gevent.joinall([recv_thread])
