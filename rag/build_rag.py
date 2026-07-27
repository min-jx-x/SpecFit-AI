import json
import os
import logging
import boto3
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

NCP_ACCESS_KEY = os.getenv("NCP_ACCESS_KEY", "")
NCP_SECRET_KEY = os.getenv("NCP_SECRET_KEY", "")
NCP_ENDPOINT_URL = "https://kr.object.ncloudstorage.com"
BUCKET_NAME = os.getenv("BUCKET_NAME", "")

DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_SAVE_PATH = os.path.join(BASE_DIR, "../data/passed_specs.json")

embedding_model = SentenceTransformer("jhgan/ko-sroberta-multitask")


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=NCP_ENDPOINT_URL,
        aws_access_key_id=NCP_ACCESS_KEY,
        aws_secret_access_key=NCP_SECRET_KEY
    )


def get_db_connection(reset_table: bool = False):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        if reset_table:
            cursor.execute("DROP TABLE IF EXISTS passed_specs;")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS passed_specs (
                id VARCHAR(100) PRIMARY KEY,
                company VARCHAR(100),
                job_category VARCHAR(100),
                gpa VARCHAR(20),
                toeic VARCHAR(20),
                toeic_speaking VARCHAR(20),
                opic VARCHAR(20),
                certificate VARCHAR(50),
                internship VARCHAR(50),
                experience_summary TEXT,
                embedding VECTOR(768)
            );
        """)
        conn.commit()
        cursor.close()

        register_vector(conn)
        return conn

    except Exception as e:
        logger.error(f"❌ PostgreSQL DB 접속 실패: {e}")
        raise e


def fetch_and_save_formatted_specs() -> list:
    s3 = get_s3_client()
    formatted_specs_list = []

    try:
        paginator = s3.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=BUCKET_NAME)

        idx = 0
        for page in page_iterator:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                file_key = obj['Key']
                
                if file_key.endswith('.json'):
                    try:
                        file_obj = s3.get_object(Bucket=BUCKET_NAME, Key=file_key)
                        data = json.loads(file_obj['Body'].read().decode('utf-8'))
                        
                        images = data.get("images", [])
                        if not images:
                            continue
                        
                        image_data = images[0]
                        
                        company_name = "미지정"
                        title_info = image_data.get("title")
                        if isinstance(title_info, dict):
                            company_name = title_info.get("inferText", "미지정")

                        fields_list = image_data.get("fields", [])
                        field_map = {}
                        for f in fields_list:
                            name = f.get("name")
                            value = f.get("inferText", "N/A")
                            if name:
                                field_map[name] = value

                        exp_summary = (
                            f"학점 {field_map.get('학점', 'N/A')}, 토익 {field_map.get('토익', 'N/A')}, "
                            f"토스 {field_map.get('토익스피킹', 'N/A')}, OPIC {field_map.get('OPIC', 'N/A')}, "
                            f"자격증 {field_map.get('자격증', 'N/A')}, 인턴 {field_map.get('인턴', 'N/A')}, "
                            f"수상내역 {field_map.get('수상내역', 'N/A')}, 교내/사회/봉사 {field_map.get('교내 사회 봉사', 'N/A')}"
                        )

                        clean_spec = {
                            "id": str(data.get("requestId", f"spec_{idx}_{file_key.replace('/', '_')}")),
                            "company": str(company_name),
                            "job_category": str(field_map.get("직무", "SW개발/백엔드")),
                            "gpa": str(field_map.get("학점", "N/A")),
                            "toeic": str(field_map.get("토익", "N/A")),
                            "toeic_speaking": str(field_map.get("토익스피킹", "N/A")),
                            "opic": str(field_map.get("OPIC", "N/A")),
                            "certificate": str(field_map.get("자격증", "N/A")),
                            "internship": str(field_map.get("인턴", "N/A")),
                            "experience_summary": exp_summary
                        }
                        
                        formatted_specs_list.append(clean_spec)
                        idx += 1

                    except Exception as e:
                        logger.error(f"파일 파싱 중 에러 ({file_key}): {e}")
                        continue

    except Exception as e:
        logger.error(f"S3 Object Storage 불러오기 실패: {e}")
        return []

    os.makedirs(os.path.dirname(JSON_SAVE_PATH), exist_ok=True)
    with open(JSON_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(formatted_specs_list, f, ensure_ascii=False, indent=2)

    logger.info(f"성공적으로 {len(formatted_specs_list)}개의 스펙 데이터를 JSON으로 저장했습니다.")
    return formatted_specs_list


def build_vector_db_from_json(reset_table: bool = True) -> bool:
    if not os.path.exists(JSON_SAVE_PATH):
        logger.error(f"저장된 JSON 파일이 없습니다: {JSON_SAVE_PATH}")
        return False

    with open(JSON_SAVE_PATH, "r", encoding="utf-8") as f:
        specs_data = json.load(f)

    if not specs_data:
        return False

    try:
        conn = get_db_connection(reset_table=reset_table)
        cursor = conn.cursor()

        upsert_query = """
            INSERT INTO passed_specs (
                id, company, job_category, gpa, toeic, toeic_speaking, 
                opic, certificate, internship, experience_summary, embedding
            ) VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                company = EXCLUDED.company,
                job_category = EXCLUDED.job_category,
                gpa = EXCLUDED.gpa,
                toeic = EXCLUDED.toeic,
                toeic_speaking = EXCLUDED.toeic_speaking,
                opic = EXCLUDED.opic,
                certificate = EXCLUDED.certificate,
                internship = EXCLUDED.internship,
                experience_summary = EXCLUDED.experience_summary,
                embedding = EXCLUDED.embedding;
        """

        records = []
        for item in specs_data:
            summary_doc = (
                f"기업명: {item.get('company', '')} | 직무: {item.get('job_category', '')} | "
                f"학점: {item.get('gpa', '')} | 토익: {item.get('toeic', '')} | "
                f"경험: {item.get('experience_summary', '')}"
            )
            
            embedding_vector = embedding_model.encode(summary_doc).tolist()

            records.append((
                item.get('id'),
                item.get('company', '미지정'),
                item.get('job_category', 'SW개발/백엔드'),
                item.get('gpa', 'N/A'),
                item.get('toeic', 'N/A'),
                item.get('toeic_speaking', 'N/A'),
                item.get('opic', 'N/A'),
                item.get('certificate', 'N/A'),
                item.get('internship', 'N/A'),
                item.get('experience_summary', ''),
                embedding_vector
            ))

        execute_values(cursor, upsert_query, records)
        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"🎉 PostgreSQL(pgvector)에 총 {len(records)}건의 정형화 스펙 적재 완료!")
        return True

    except Exception as e:
        logger.error(f"PostgreSQL 데이터 적재 에러: {e}")
        return False


def search_vector_db(query: str, company_filter: str = None, top_k: int = 3) -> list:
    try:
        query_vector = embedding_model.encode(query).tolist()

        conn = get_db_connection(reset_table=False)
        cursor = conn.cursor()

        if company_filter:
            sql = """
                SELECT id, company, job_category, gpa, toeic, certificate, internship, experience_summary, (embedding <=> %s::vector) AS distance
                FROM passed_specs
                WHERE company = %s
                ORDER BY distance ASC
                LIMIT %s;
            """
            cursor.execute(sql, (query_vector, company_filter, top_k))
        else:
            sql = """
                SELECT id, company, job_category, gpa, toeic, certificate, internship, experience_summary, (embedding <=> %s::vector) AS distance
                FROM passed_specs
                ORDER BY distance ASC
                LIMIT %s;
            """
            cursor.execute(sql, (query_vector, top_k))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        formatted_results = []
        for row in rows:
            formatted_results.append({
                "id": row[0],
                "company": row[1],
                "job_category": row[2],
                "gpa": row[3],
                "toeic": row[4],
                "certificate": row[5],
                "internship": row[6],
                "experience_summary": row[7],
                "distance": float(row[8]) if row[8] is not None else None
            })

        return formatted_results

    except Exception as e:
        logger.error(f"Vector 검색 실패: {e}")
        return []