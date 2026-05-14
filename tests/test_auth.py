import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def test_auth():
    async with httpx.AsyncClient(timeout=30.0) as client:

        # ========== 1. 보호자 로그인 ==========
        print("=" * 50)
        print("1️⃣ 보호자 로그인 (guardian_001)")
        print("=" * 50)
        response = await client.post(f"{BASE_URL}/auth/login", json={
            "username": "guardian_001",
            "password": "test1234"
        })
        print(f"상태코드: {response.status_code}")
        guardian_data = response.json()
        print(f"응답: {guardian_data}")
        
        if response.status_code != 200:
            print("❌ 보호자 로그인 실패!")
            return
        
        guardian_token = guardian_data["access_token"]
        print(f"✅ 보호자 토큰: {guardian_token[:30]}...\n")

        # ========== 2. 환자 로그인 ==========
        print("=" * 50)
        print("2️⃣ 환자 로그인 (patient_001)")
        print("=" * 50)
        response = await client.post(f"{BASE_URL}/auth/login", json={
            "username": "patient_001",
            "password": "test1234"
        })
        print(f"상태코드: {response.status_code}")
        patient_data = response.json()
        print(f"응답: {patient_data}")
        
        if response.status_code != 200:
            print("❌ 환자 로그인 실패!")
            return
        
        patient_token = patient_data["access_token"]
        print(f"✅ 환자 토큰: {patient_token[:30]}...\n")

        # ========== 3. 보호자 정보 조회 ==========
        print("=" * 50)
        print("3️⃣ 보호자 정보 조회")
        print("=" * 50)
        response = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {guardian_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}\n")

        # ========== 4. 환자 정보 조회 ==========
        print("=" * 50)
        print("4️⃣ 환자 정보 조회")
        print("=" * 50)
        response = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {patient_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}\n")

        # ========== 5. 환자 연결 ==========
        print("=" * 50)
        print("5️⃣ 보호자가 환자 연결 (patient_001)")
        print("=" * 50)
        response = await client.post(
            f"{BASE_URL}/auth/connect-patient",
            json={"patient_username": "patient_001"},
            headers={"Authorization": f"Bearer {guardian_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}\n")

        # ========== 6. 연결 후 환자 정보 조회 ==========
        print("=" * 50)
        print("6️⃣ 연결 후 환자 정보 조회 (guardian_id 확인)")
        print("=" * 50)
        response = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {patient_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}\n")

        print("=" * 50)
        print("✅ 모든 테스트 완료!")
        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_auth())