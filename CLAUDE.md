# คำแนะนำสำหรับ AI ในโปรเจกต์นี้

## Database (PostgreSQL)

- เชื่อมต่อ DB ผ่าน Tailscale tunnel (`DB_HOST` ใน `.env` เป็น Tailscale hostname/IP) ทำให้แต่ละ
  connection ใหม่มี overhead จาก network RTT + auth handshake รวมกัน ~70-90ms ต่อครั้ง (วัดจริงด้วย
  `diagnose_db_latency.py`) ในขณะที่ query เดียวบน connection ที่เปิดอยู่แล้วใช้เวลาแค่ ~10ms
- ด้วยเหตุนี้ **ห้ามเปิด-ปิด `psycopg2.connect()` ใหม่ทุกครั้งที่ทำงานกับ DB** ถ้าเป็นไปได้ให้ใช้
  connection pool เสมอ
- `db_handler.py` มี connection pool อยู่แล้ว (`psycopg2.pool.SimpleConnectionPool` ผ่านฟังก์ชัน
  `get_connection()` / `release_connection()`) — ฟังก์ชันใหม่ๆ ที่ต้องคุย DB ให้เรียกใช้คู่นี้แทนการ
  เปิด connection เอง และห้ามเรียก `conn.close()` ตรงๆ กับ connection ที่ได้จาก pool (ให้เรียก
  `release_connection(conn)` แทน เพื่อคืน connection กลับ pool ไม่ใช่ปิดทิ้งจริง)
- ถ้าจะเขียนสคริปต์ทดสอบ/diagnostic ใหม่ที่ต้องต่อ DB เอง (ไม่ผ่าน `db_handler.py`) เช่นต้องการวัด
  raw connection overhead ก็ทำได้ แต่ให้ระบุชัดในโค้ด/คอมเมนต์ว่าเป็นการทดสอบ ไม่ใช่ pattern ที่ควร
  ใช้ใน production code
