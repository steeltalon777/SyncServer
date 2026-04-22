#!/usr/bin/env python3
"""
Скрипт для полной проверки CRUD всех API endpoints SyncServer.
Использует библиотеку requests для отправки HTTP запросов.
Генерирует отчет в формате markdown.
"""

import os
import sys
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('api_crud_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
BASE_URL = os.environ.get('SYNCSERVER_BASE_URL', 'http://127.0.0.1:8000/api/v1')
HEADERS = {
    'X-User-Token': '9d5c0496-a32b-4d55-be0d-1fcfede4fd5a',
    'X-Device-Token': '9eed7417-a854-4d9a-90ed-3d3c98714e07',
    'Content-Type': 'application/json'
}

# Глобальные переменные для хранения созданных тестовых данных
test_data = {
    'site_id': None,
    'unit_id': None,
    'category_id': None,
    'item_id': None,
    'recipient_id': None,
    'operation_id': None,
    'document_id': None,
    'device_id': None,
    'user_id': None,
    'scope_id': None,
}

# Результаты тестов
@dataclass
class TestResult:
    endpoint: str
    method: str
    status_code: int
    expected_status: List[int]
    success: bool
    response_time_ms: float
    error_message: Optional[str] = None
    response_data: Optional[Dict] = None

test_results: List[TestResult] = []


def make_request(method: str, endpoint: str, **kwargs) -> Tuple[Optional[Dict], int, float]:
    """Универсальная функция для выполнения HTTP запроса."""
    url = f"{BASE_URL}{endpoint}"
    headers = kwargs.pop('headers', HEADERS)
    
    start_time = time.time()
    try:
        response = requests.request(method, url, headers=headers, **kwargs)
        response_time = (time.time() - start_time) * 1000
        
        logger.info(f"{method} {endpoint} -> {response.status_code} ({response_time:.0f}ms)")
        if response.status_code >= 400:
            logger.warning(f"Response body: {response.text[:500]}")
        
        try:
            data = response.json() if response.content else {}
        except json.JSONDecodeError:
            data = {"raw": response.text[:200]}
        
        return data, response.status_code, response_time
    except requests.exceptions.RequestException as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Request failed: {e}")
        return {"error": str(e)}, 0, response_time


def record_test(endpoint: str, method: str, status_code: int, expected_status: List[int], 
                response_time_ms: float, error_message: Optional[str] = None,
                response_data: Optional[Dict] = None) -> TestResult:
    """Запись результата теста."""
    success = status_code in expected_status
    result = TestResult(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        expected_status=expected_status,
        success=success,
        response_time_ms=response_time_ms,
        error_message=error_message,
        response_data=response_data
    )
    test_results.append(result)
    
    if success:
        logger.info(f"[OK] {method} {endpoint} - успех ({status_code})")
    else:
        logger.error(f"[FAIL] {method} {endpoint} - провал ({status_code}, ожидалось {expected_status})")
        if error_message:
            logger.error(f"   Ошибка: {error_message}")
    
    return result


def test_health():
    """Проверка health endpoints."""
    logger.info("=== Health endpoints ===")
    
    endpoints = [
        ('/health', 'GET', [200]),
        ('/ready', 'GET', [200]),
        ('/health/detailed', 'GET', [200]),
    ]
    
    for endpoint, method, expected in endpoints:
        data, status, rt = make_request(method, endpoint)
        record_test(endpoint, method, status, expected, rt)


def test_auth():
    """Проверка auth endpoints."""
    logger.info("=== Auth endpoints ===")
    
    # GET endpoints
    get_endpoints = [
        ('/auth/me', [200]),
        ('/auth/sites', [200]),
        ('/auth/context', [200]),
    ]
    
    for endpoint, expected in get_endpoints:
        data, status, rt = make_request('GET', endpoint)
        record_test(endpoint, 'GET', status, expected, rt)
    
    # POST /auth/sync-user
    payload = {
        "username": f"testuser_{int(time.time())}",
        "email": f"test{int(time.time())}@example.com",
        "full_name": "Test User",
        "role": "storekeeper"
    }
    data, status, rt = make_request('POST', '/auth/sync-user', json=payload)
    record_test('/auth/sync-user', 'POST', status, [200, 201], rt)
    if status in [200, 201] and data.get('id'):
        test_data['user_id'] = data['id']


def test_admin_sites_crud():
    """CRUD для sites."""
    logger.info("=== Admin Sites CRUD ===")
    
    # GET /admin/sites
    data, status, rt = make_request('GET', '/admin/sites')
    record_test('/admin/sites', 'GET', status, [200], rt)
    
    # POST /admin/sites
    timestamp = int(time.time())
    payload = {
        "code": f"TEST{timestamp}",
        "name": f"Test Site {timestamp}",
        "is_active": True
    }
    data, status, rt = make_request('POST', '/admin/sites', json=payload)
    record_test('/admin/sites', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['site_id'] = data['id']
        logger.info(f"Создан site с ID: {test_data['site_id']}")
    
    # PATCH /admin/sites/{site_id}
    if test_data['site_id']:
        payload = {"name": f"Updated Site {timestamp}"}
        data, status, rt = make_request('PATCH', f"/admin/sites/{test_data['site_id']}", json=payload)
        record_test('/admin/sites/{site_id}', 'PATCH', status, [200], rt)


def test_admin_users_crud():
    """CRUD для users."""
    logger.info("=== Admin Users CRUD ===")
    
    # GET /admin/users
    data, status, rt = make_request('GET', '/admin/users')
    record_test('/admin/users', 'GET', status, [200], rt)
    
    # POST /admin/users
    timestamp = int(time.time())
    payload = {
        "username": f"adminuser_{timestamp}",
        "email": f"admin{timestamp}@example.com",
        "full_name": "Admin Test User",
        "role": "storekeeper",
        "is_active": True
    }
    data, status, rt = make_request('POST', '/admin/users', json=payload)
    record_test('/admin/users', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['user_id'] = data['id']
    
    # GET /admin/users/{user_id}
    if test_data['user_id']:
        data, status, rt = make_request('GET', f"/admin/users/{test_data['user_id']}")
        record_test('/admin/users/{user_id}', 'GET', status, [200], rt)
    
    # PATCH /admin/users/{user_id}
    if test_data['user_id']:
        payload = {"full_name": "Updated Name"}
        data, status, rt = make_request('PATCH', f"/admin/users/{test_data['user_id']}", json=payload)
        record_test('/admin/users/{user_id}', 'PATCH', status, [200], rt)


def test_admin_access_scopes_crud():
    """CRUD для access scopes."""
    logger.info("=== Admin Access Scopes CRUD ===")
    
    # GET /admin/access/scopes
    data, status, rt = make_request('GET', '/admin/access/scopes')
    record_test('/admin/access/scopes', 'GET', status, [200], rt)
    
    # POST /admin/access/scopes
    timestamp = int(time.time())
    payload = {
        "name": f"Test Scope {timestamp}",
        "site_ids": [test_data['site_id']] if test_data['site_id'] else [],
        "permissions": ["catalog.read", "operations.read"]
    }
    data, status, rt = make_request('POST', '/admin/access/scopes', json=payload)
    record_test('/admin/access/scopes', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['scope_id'] = data['id']
    
    # PATCH /admin/access/scopes/{scope_id}
    if test_data['scope_id']:
        payload = {"name": f"Updated Scope {timestamp}"}
        data, status, rt = make_request('PATCH', f"/admin/access/scopes/{test_data['scope_id']}", json=payload)
        record_test('/admin/access/scopes/{scope_id}', 'PATCH', status, [200], rt)


def test_admin_devices_crud():
    """CRUD для devices."""
    logger.info("=== Admin Devices CRUD ===")
    
    # GET /admin/devices
    data, status, rt = make_request('GET', '/admin/devices')
    record_test('/admin/devices', 'GET', status, [200], rt)
    
    # POST /admin/devices
    timestamp = int(time.time())
    payload = {
        "name": f"Test Device {timestamp}",
        "site_id": test_data['site_id'],
        "type": "mobile"
    }
    data, status, rt = make_request('POST', '/admin/devices', json=payload)
    record_test('/admin/devices', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['device_id'] = data['id']
        logger.info(f"Создан device с ID: {test_data['device_id']}")
    
    # GET /admin/devices/{device_id}
    if test_data['device_id']:
        data, status, rt = make_request('GET', f"/admin/devices/{test_data['device_id']}")
        record_test('/admin/devices/{device_id}', 'GET', status, [200], rt)
    
    # PATCH /admin/devices/{device_id}
    if test_data['device_id']:
        payload = {"name": f"Updated Device {timestamp}"}
        data, status, rt = make_request('PATCH', f"/admin/devices/{test_data['device_id']}", json=payload)
        record_test('/admin/devices/{device_id}', 'PATCH', status, [200], rt)


def test_catalog_admin_units_crud():
    """CRUD для units."""
    logger.info("=== Catalog Admin Units CRUD ===")
    
    # GET /catalog/admin/units
    data, status, rt = make_request('GET', '/catalog/admin/units')
    record_test('/catalog/admin/units', 'GET', status, [200], rt)
    
    # POST /catalog/admin/units
    timestamp = int(time.time())
    payload = {
        "code": f"UNIT{timestamp}",
        "name": f"Test Unit {timestamp}",
        "symbol": "pcs"
    }
    data, status, rt = make_request('POST', '/catalog/admin/units', json=payload)
    record_test('/catalog/admin/units', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['unit_id'] = data['id']
        logger.info(f"Создан unit с ID: {test_data['unit_id']}")
    
    # GET /catalog/admin/units/{unit_id}
    if test_data['unit_id']:
        data, status, rt = make_request('GET', f"/catalog/admin/units/{test_data['unit_id']}")
        record_test('/catalog/admin/units/{unit_id}', 'GET', status, [200], rt)
    
    # PATCH /catalog/admin/units/{unit_id}
    if test_data['unit_id']:
        payload = {"name": f"Updated Unit {timestamp}"}
        data, status, rt = make_request('PATCH', f"/catalog/admin/units/{test_data['unit_id']}", json=payload)
        record_test('/catalog/admin/units/{unit_id}', 'PATCH', status, [200], rt)


def test_catalog_admin_categories_crud():
    """CRUD для categories."""
    logger.info("=== Catalog Admin Categories CRUD ===")
    
    # GET /catalog/admin/categories
    data, status, rt = make_request('GET', '/catalog/admin/categories')
    record_test('/catalog/admin/categories', 'GET', status, [200], rt)
    
    # POST /catalog/admin/categories
    timestamp = int(time.time())
    payload = {
        "code": f"CAT{timestamp}",
        "name": f"Test Category {timestamp}",
        "parent_id": None
    }
    data, status, rt = make_request('POST', '/catalog/admin/categories', json=payload)
    record_test('/catalog/admin/categories', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['category_id'] = data['id']
        logger.info(f"Создан category с ID: {test_data['category_id']}")
    
    # GET /catalog/admin/categories/{category_id}
    if test_data['category_id']:
        data, status, rt = make_request('GET', f"/catalog/admin/categories/{test_data['category_id']}")
        record_test('/catalog/admin/categories/{category_id}', 'GET', status, [200], rt)
    
    # PATCH /catalog/admin/categories/{category_id}
    if test_data['category_id']:
        payload = {"name": f"Updated Category {timestamp}"}
        data, status, rt = make_request('PATCH', f"/catalog/admin/categories/{test_data['category_id']}", json=payload)
        record_test('/catalog/admin/categories/{category_id}', 'PATCH', status, [200], rt)


def test_catalog_admin_items_crud():
    """CRUD для items."""
    logger.info("=== Catalog Admin Items CRUD ===")
    
    # GET /catalog/admin/items
    data, status, rt = make_request('GET', '/catalog/admin/items')
    record_test('/catalog/admin/items', 'GET', status, [200], rt)
    
    # POST /catalog/admin/items
    timestamp = int(time.time())
    payload = {
        "code": f"ITEM{timestamp}",
        "name": f"Test Item {timestamp}",
        "category_id": test_data['category_id'],
        "unit_id": test_data['unit_id'],
        "is_active": True
    }
    data, status, rt = make_request('POST', '/catalog/admin/items', json=payload)
    record_test('/catalog/admin/items', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['item_id'] = data['id']
        logger.info(f"Создан item с ID: {test_data['item_id']}")
    
    # GET /catalog/admin/items/{item_id}
    if test_data['item_id']:
        data, status, rt = make_request('GET', f"/catalog/admin/items/{test_data['item_id']}")
        record_test('/catalog/admin/items/{item_id}', 'GET', status, [200], rt)
    
    # PATCH /catalog/admin/items/{item_id}
    if test_data['item_id']:
        payload = {"name": f"Updated Item {timestamp}"}
        data, status, rt = make_request('PATCH', f"/catalog/admin/items/{test_data['item_id']}", json=payload)
        record_test('/catalog/admin/items/{item_id}', 'PATCH', status, [200], rt)


def test_recipients_crud():
    """CRUD для recipients."""
    logger.info("=== Recipients CRUD ===")
    
    # GET /recipients
    data, status, rt = make_request('GET', '/recipients')
    record_test('/recipients', 'GET', status, [200], rt)
    
    # POST /recipients
    timestamp = int(time.time())
    payload = {
        "name": f"Test Recipient {timestamp}",
        "recipient_type": "person",
        "external_id": f"EXT{timestamp}",
        "is_active": True
    }
    data, status, rt = make_request('POST', '/recipients', json=payload)
    record_test('/recipients', 'POST', status, [201], rt)
    if status == 201 and data.get('id'):
        test_data['recipient_id'] = data['id']
        logger.info(f"Создан recipient с ID: {test_data['recipient_id']}")
    
    # GET /recipients/{recipient_id}
    if test_data['recipient_id']:
        data, status, rt = make_request('GET', f"/recipients/{test_data['recipient_id']}")
        record_test('/recipients/{recipient_id}', 'GET', status, [200], rt)
    
    # PATCH /recipients/{recipient_id}
    if test_data['recipient_id']:
        payload = {"name": f"Updated Recipient {timestamp}"}
        data, status, rt = make_request('PATCH', f"/recipients/{test_data['recipient_id']}", json=payload)
        record_test('/recipients/{recipient_id}', 'PATCH', status, [200], rt)


def test_operations_crud():
    """CRUD для operations."""
    logger.info("=== Operations CRUD ===")
    
    # GET /operations
    data, status, rt = make_request('GET', '/operations')
    record_test('/operations', 'GET', status, [200], rt)
    
    # POST /operations (создание операции)
    if test_data['site_id'] and test_data['item_id']:
        timestamp = int(time.time())
        payload = {
            "operation_type": "transfer",
            "source_site_id": test_data['site_id'],
            "destination_site_id": test_data['site_id'],
            "effective_at": datetime.now().isoformat(),
            "lines": [
                {
                    "item_id": test_data['item_id'],
                    "qty": 10.0,
                    "unit_id": test_data['unit_id']
                }
            ]
        }
        data, status, rt = make_request('POST', '/operations', json=payload)
        record_test('/operations', 'POST', status, [201], rt)
        if status == 201 and data.get('id'):
            test_data['operation_id'] = data['id']
            logger.info(f"Создана операция с ID: {test_data['operation_id']}")
    
    # GET /operations/{operation_id}
    if test_data['operation_id']:
        data, status, rt = make_request('GET', f"/operations/{test_data['operation_id']}")
        record_test('/operations/{operation_id}', 'GET', status, [200], rt)


def test_balances():
    """Проверка балансов."""
    logger.info("=== Balances ===")
    
    # GET /balances
    data, status, rt = make_request('GET', '/balances')
    record_test('/balances', 'GET', status, [200], rt)
    
    # GET /balances/by-site
    if test_data['site_id']:
        data, status, rt = make_request('GET', f"/balances/by-site?site_id={test_data['site_id']}")
        record_test('/balances/by-site', 'GET', status, [200], rt)
    
    # GET /balances/summary
    data, status, rt = make_request('GET', '/balances/summary')
    record_test('/balances/summary', 'GET', status, [200], rt)


def test_asset_register():
    """Проверка реестра активов."""
    logger.info("=== Asset Register ===")
    
    # GET /pending-acceptance
    data, status, rt = make_request('GET', '/pending-acceptance')
    record_test('/pending-acceptance', 'GET', status, [200], rt)
    
    # GET /lost-assets
    data, status, rt = make_request('GET', '/lost-assets')
    record_test('/lost-assets', 'GET', status, [200], rt)
    
    # GET /issued-assets
    data, status, rt = make_request('GET', '/issued-assets')
    record_test('/issued-assets', 'GET', status, [200], rt)


def test_documents():
    """Проверка документов."""
    logger.info("=== Documents ===")
    
    # GET /documents
    data, status, rt = make_request('GET', '/documents')
    record_test('/documents', 'GET', status, [200], rt)
    
    # POST /documents/generate (если есть операция)
    if test_data['operation_id']:
        payload = {
            "operation_id": test_data['operation_id'],
            "document_type": "waybill"
        }
        data, status, rt = make_request('POST', '/documents/generate', json=payload)
        record_test('/documents/generate', 'POST', status, [201], rt)
        if status == 201 and data.get('id'):
            test_data['document_id'] = data['id']
            logger.info(f"Создан документ с ID: {test_data['document_id']}")
    
    # GET /documents/{document_id}
    if test_data['document_id']:
        data, status, rt = make_request('GET', f"/documents/{test_data['document_id']}")
        record_test('/documents/{document_id}', 'GET', status, [200], rt)


def test_reports():
    """Проверка отчетов."""
    logger.info("=== Reports ===")
    
    # GET /reports/item-movement
    end_date = datetime.now().date().isoformat()
    start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    data, status, rt = make_request('GET', f"/reports/item-movement?start_date={start_date}&end_date={end_date}")
    record_test('/reports/item-movement', 'GET', status, [200], rt)
    
    # GET /reports/stock-summary
    data, status, rt = make_request('GET', '/reports/stock-summary')
    record_test('/reports/stock-summary', 'GET', status, [200], rt)


def test_sync():
    """Проверка синхронизации."""
    logger.info("=== Sync ===")
    
    # POST /ping
    payload = {
        "device_id": test_data['device_id'],
        "seq": 1
    }
    data, status, rt = make_request('POST', '/ping', json=payload)
    record_test('/ping', 'POST', status, [200], rt)
    
    # POST /pull
    payload = {
        "device_id": test_data['device_id'],
        "since_seq": 0
    }
    data, status, rt = make_request('POST', '/pull', json=payload)
    record_test('/pull', 'POST', status, [200], rt)


def generate_report():
    """Генерация отчета в формате markdown."""
    logger.info("=== Генерация отчета ===")
    
    total_tests = len(test_results)
    successful_tests = sum(1 for r in test_results if r.success)
    failed_tests = total_tests - successful_tests
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    
    report_lines = []
    report_lines.append("# Отчет тестирования API SyncServer")
    report_lines.append("")
    report_lines.append(f"**Дата тестирования:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**Базовый URL:** {BASE_URL}")
    report_lines.append("")
    report_lines.append("## Статистика")
    report_lines.append("")
    report_lines.append(f"- Всего тестов: {total_tests}")
    report_lines.append(f"- Успешных: {successful_tests}")
    report_lines.append(f"- Проваленных: {failed_tests}")
    report_lines.append(f"- Успешность: {success_rate:.1f}%")
    report_lines.append("")
    report_lines.append("## Детали тестов")
    report_lines.append("")
    report_lines.append("| Endpoint | Method | Status | Expected | Success | Response Time |")
    report_lines.append("|----------|--------|--------|----------|---------|---------------|")
    
    for result in test_results:
        status_display = result.status_code if result.status_code > 0 else "ERROR"
        expected_display = ",".join(str(s) for s in result.expected_status)
        success_display = "✓" if result.success else "✗"
        response_time = f"{result.response_time_ms:.0f}ms"
        report_lines.append(f"| {result.endpoint} | {result.method} | {status_display} | {expected_display} | {success_display} | {response_time} |")
    
    report_lines.append("")
    report_lines.append("## Созданные тестовые данные")
    report_lines.append("")
    for key, value in test_data.items():
        if value:
            report_lines.append(f"- {key}: {value}")
    
    report_lines.append("")
    report_lines.append("## Логи")
    report_lines.append("")
    report_lines.append("Полные логи доступны в файле `api_crud_test.log`")
    
    report_content = "\n".join(report_lines)
    
    with open('api_crud_test_report.md', 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    logger.info(f"Отчет сохранен в файл: api_crud_test_report.md")
    logger.info(f"Статистика: {successful_tests}/{total_tests} успешных тестов ({success_rate:.1f}%)")


def main():
    """Основная функция выполнения тестов."""
    logger.info("Начало тестирования API SyncServer")
    logger.info(f"Базовый URL: {BASE_URL}")
    
    try:
        # Выполнение тестов в правильном порядке
        test_health()
        test_auth()
        test_admin_sites_crud()
        test_admin_users_crud()
        test_admin_access_scopes_crud()
        test_admin_devices_crud()
        test_catalog_admin_units_crud()
        test_catalog_admin_categories_crud()
        test_catalog_admin_items_crud()
        test_recipients_crud()
        test_operations_crud()
        test_balances()
        test_asset_register()
        test_documents()
        test_reports()
        test_sync()
        
        # Генерация отчета
        generate_report()
        
        # Итоговая статистика
        total = len(test_results)
        successful = sum(1 for r in test_results if r.success)
        logger.info(f"Тестирование завершено. Успешных тестов: {successful}/{total}")
        
        if successful == total:
            logger.info("[SUCCESS] Все тесты прошли успешно!")
            return 0
        else:
            logger.error(f"[FAILURE] Некоторые тесты провалились: {total - successful}")
            return 1
            
    except Exception as e:
        logger.error(f"Критическая ошибка во время тестирования: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
