import socket
import json
import threading
import struct
from minotaurx_hash import getPoWHash  # Thư viện đã build

class Miner:
    def __init__(self, pool_url, wallet, port, password, threads):
        self.pool_url = pool_url.replace("stratum+tcp://", "")  # Loại bỏ tiền tố giao thức
        self.wallet = wallet
        self.port = port
        self.password = password
        self.threads = threads
        self.connection = None
        self.job = None
        self.extranonce1 = None
        self.extranonce2_size = None
        self.difficulty = 1  # Gán giá trị mặc định cho difficulty
        self.running = True

    def connect(self):
        """Kết nối tới pool"""
        try:
            self.connection = socket.create_connection((self.pool_url, self.port))
            print(f"Kết nối thành công tới {self.pool_url}:{self.port}")
        except Exception as e:
            print(f"Lỗi khi kết nối tới pool: {e}")
            self.running = False

    def subscribe(self):
        """Gửi yêu cầu subscribe tới pool"""
        try:
            self.send_json({
                "id": 1,
                "method": "mining.subscribe",
                "params": []
            })
            response = self.receive_json()
            if response and "result" in response:
                self.extranonce1 = response["result"][1]
                self.extranonce2_size = response["result"][2]
                print("Đăng ký thành công.")
        except Exception as e:
            print(f"Lỗi khi đăng ký: {e}")
            self.running = False

    def authorize(self):
        """Gửi yêu cầu đăng nhập (authorize)"""
        try:
            self.send_json({
                "id": 2,
                "method": "mining.authorize",
                "params": [self.wallet, self.password]
            })
            response = self.receive_json()
            if response and response.get("result", False):
                print("Đăng nhập thành công.")
            else:
                print("Lỗi khi đăng nhập.")
                self.running = False
        except Exception as e:
            print(f"Lỗi khi đăng nhập: {e}")
            self.running = False

    def send_json(self, data):
        """Gửi dữ liệu JSON tới pool"""
        self.connection.sendall((json.dumps(data) + "\n").encode())

    def receive_json(self):
        """Nhận dữ liệu JSON từ pool"""
        response = self.connection.recv(1024).decode()
        for line in response.splitlines():
            return json.loads(line)

    def handle_jobs(self):
        """Nhận công việc mới từ pool"""
        while self.running:
            try:
                response = self.receive_json()
                if response and response.get("method") == "mining.notify":
                    self.job = response["params"]
                    self.difficulty = 1  # Gán giá trị mặc định cho difficulty
                    print(f"Nhận công việc mới: {self.job[0]}")
            except Exception as e:
                print(f"Lỗi khi nhận công việc: {e}")
                self.running = False

    def mine(self, thread_id):
        """Thực hiện tính toán hash và tìm nonce hợp lệ"""
        while self.running:
            if self.job:
                job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs = self.job
                extranonce2 = f"{thread_id:0{self.extranonce2_size * 2}x}"
                coinbase = coinb1 + self.extranonce1 + extranonce2 + coinb2
                coinbase_hash_bin = getPoWHash(bytes.fromhex(coinbase))
                merkle_root = coinbase_hash_bin.hex()
                for branch in merkle_branch:
                    merkle_root = getPoWHash(bytes.fromhex(merkle_root + branch)).hex()

                blockheader = version + prevhash + merkle_root + nbits + ntime + "00000000"
                
                # Gọi hàm để tìm nonce hợp lệ
                valid_nonce, blockhash = self.find_valid_nonce(blockheader)
                
                if valid_nonce is not None:
                    print(f"[Thread {thread_id}] Đào được block! {blockhash.hex()}")
                    self.send_json({
                        "id": 4,
                        "method": "mining.submit",
                        "params": [self.wallet, job_id, extranonce2, ntime, "00000000"]
                    })
                else:
                    print(f"[Thread {thread_id}] Không tìm thấy nonce hợp lệ.")

    def find_valid_nonce(self, blockheader):
        """Tìm nonce hợp lệ cho khối"""
        nonce = 0
        max_nonce = 0xFFFFFFFF  # Giá trị tối đa của nonce (32-bit)
        
        target_difficulty = 1  # Độ khó mục tiêu, có thể thay đổi theo độ khó của pool
        
        while nonce <= max_nonce:
            # Tạo header mới bằng cách thêm nonce vào header gốc
            full_header = blockheader + struct.pack("<I", nonce)

            # Tính hash PoW
            hash_result = getPoWHash(full_header)

            # Chuyển đổi hash về số nguyên lớn để so sánh với target
            hash_int = int.from_bytes(hash_result, byteorder="big")

            # Kiểm tra nếu hash thỏa mãn độ khó
            if hash_int < target_difficulty:
                return nonce, hash_result  # Trả về nonce hợp lệ và hash tương ứng

            nonce += 1

        return None, None  # Không tìm được nonce hợp lệ

    def start(self):
        """Bắt đầu đào coin"""
        self.connect()
        if self.running:
            self.subscribe()
        if self.running:
            self.authorize()

        if self.running:
            # Chạy luồng nhận công việc
            threading.Thread(target=self.handle_jobs, daemon=True).start()
            # Tạo các luồng đào
            threads = []
            for i in range(self.threads):
                thread = threading.Thread(target=self.mine, args=(i,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()


if __name__ == "__main__":
    pool = "stratum+tcp://minotaurx.na.mine.zpool.ca:7019"
    wallet = "R9uHDn9XXqPAe2TLsEmVoNrokmWsHREV2Q"
    password = "c=RVN"  # Mật khẩu cho pool
    port = 7019
    threads = int(input("Nhập số luồng đào: "))

    miner = Miner(pool, wallet, port, password, threads)
    miner.start()
