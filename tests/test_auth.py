import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def test_auth_complete():
    async with httpx.AsyncClient(timeout=30.0) as client:

        # ========== 1. 보호자 로그인 ==========
        print("=" * 60)
        print("1️⃣ 보호자 로그인 (guardian_001 / test1234)")
        print("=" * 60)
        response = await client.post(f"{BASE_URL}/auth/login", json={
            "username": "guardian_001",
            "password": "test1234"
        })
        print(f"상태코드: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ 실패: {response.json()}")
            return
        
        guardian_data = response.json()
        guardian_token = guardian_data["access_token"]
        print(f"✅ 성공")
        print(f"   이름: {guardian_data['name']}")
        print(f"   역할: {guardian_data['role']}")
        print()

        # ========== 2. 환자 로그인 (초대코드로) ==========
        print("=" * 60)
        print("2️⃣ 환자 초대코드 로그인 (ABC123-001)")
        print("=" * 60)
        response = await client.post(f"{BASE_URL}/auth/login-with-code", json={
            "invitation_code": "ABC123-001"
        })
        print(f"상태코드: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ 실패: {response.json()}")
            return
        
        patient_data = response.json()
        patient_token = patient_data["access_token"]
        print(f"✅ 성공")
        print(f"   이름: {patient_data['name']}")
        print(f"   역할: {patient_data['role']}")
        print()

        # ========== 3. 보호자 정보 조회 ==========
        print("=" * 60)
        print("3️⃣ 보호자 정보 조회")
        print("=" * 60)
        response = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {guardian_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}")
        print()

        # ========== 4. 환자 정보 조회 ==========
        print("=" * 60)
        print("4️⃣ 환자 정보 조회")
        print("=" * 60)
        response = await client.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {patient_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}")
        print()

        # ========== 5. 새로운 환자 초대 ==========
        print("=" * 60)
        print("5️⃣ 보호자가 새로운 환자 초대")
        print("=" * 60)
        response = await client.post(
            f"{BASE_URL}/auth/invite-patient",
            json={
                "patient_name": "박영희",
                "patient_phone": "010-5555-6666",
                "birth_date": "1955-06-15",
                "age": 69,
                "cognitive_symptoms": ["기억력 저하"],
                "behavioral_symptoms": ["무감정"],
                "relationship": "배우자"
            },
            headers={"Authorization": f"Bearer {guardian_token}"}
        )
        print(f"상태코드: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ 실패: {response.json()}")
        else:
            new_patient_data = response.json()
            new_invitation_code = new_patient_data["invitation_code"]
            print(f"✅ 성공")
            print(f"   새 환자 ID: {new_patient_data['patient_user_id']}")
            print(f"   초대코드: {new_invitation_code}")
            print()

            # ========== 6. 새로운 환자로 로그인 ==========
            print("=" * 60)
            print(f"6️⃣ 새로운 환자 로그인 (초대코드: {new_invitation_code})")
            print("=" * 60)
            response = await client.post(f"{BASE_URL}/auth/login-with-code", json={
                "invitation_code": new_invitation_code
            })
            print(f"상태코드: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 실패: {response.json()}")
            else:
                new_patient_token = response.json()["access_token"]
                print(f"✅ 성공")
                print(f"   이름: {response.json()['name']}")
                print()

        # ========== 7. 잘못된 초대코드 로그인 시도 ==========
        print("=" * 60)
        print("7️⃣ 잘못된 초대코드 로그인 시도")
        print("=" * 60)
        response = await client.post(f"{BASE_URL}/auth/login-with-code", json={
            "invitation_code": "INVALID-CODE"
        })
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}")
        print()

        # ========== 8. 비보호자가 환자 초대 시도 ==========
        print("=" * 60)
        print("8️⃣ 환자가 다른 환자를 초대 시도 (실패해야 함)")
        print("=" * 60)
        response = await client.post(
            f"{BASE_URL}/auth/invite-patient",
            json={
                "patient_name": "김미영",
                "patient_phone": "010-7777-8888",
                "birth_date": "1960-03-20",
                "age": 64,
                "cognitive_symptoms": [],
                "behavioral_symptoms": [],
                "relationship": "자녀"
            },
            headers={"Authorization": f"Bearer {patient_token}"}
        )
        print(f"상태코드: {response.status_code}")
        print(f"응답: {response.json()}")
        print()

        print("=" * 60)
        print("✅ 모든 테스트 완료!")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_auth_complete())