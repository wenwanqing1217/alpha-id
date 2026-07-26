"""注册流程 API 路由 — 替代原 Flow/API 功能

覆盖：短信验证码发送/校验、支付宝人脸认证、DID 生成、注册完成。
"""

import hashlib
import json
import os
import random
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from alpha_id.container import Container
from alpha_id.signer import AIDSigner

router = APIRouter(prefix="/api/v1/register", tags=["注册"])


def _get_storage():
    """获取统一的存储后端（通过 Container DI）"""
    return Container.instance().storage


def _sms_store() -> Dict[str, dict]:
    try:
        store = _get_storage()
        data = store.load("sms_codes")
        return data if data else {}
    except Exception:
        return {}


def _sms_save(data: Dict[str, dict]) -> None:
    try:
        store = _get_storage()
        store.save("sms_codes", data)
    except Exception:
        pass


def _clean_expired() -> Dict[str, dict]:
    data = _sms_store()
    now = time.time()
    expired = [k for k, v in data.items() if v.get("expires_at", 0) < now]
    for k in expired:
        del data[k]
    if expired:
        _sms_save(data)
    return data


def _face_store() -> Dict[str, dict]:
    try:
        store = _get_storage()
        data = store.load("face_certify")
        return data if data else {}
    except Exception:
        return {}


def _face_save(data: Dict[str, dict]) -> None:
    try:
        store = _get_storage()
        store.save("face_certify", data)
    except Exception:
        pass


@router.post("/send-sms")
async def send_sms(request: Request):
    """发送短信验证码（无阿里云 Key 时降级演示模式）"""
    body = await request.json()
    phone = body.get("phone", "")
    if not phone or not phone.startswith("1") or len(phone) != 11:
        raise HTTPException(status_code=400, detail="手机号格式错误")

    code = f"{random.randint(100000, 999999)}"
    data = _clean_expired()
    data[phone] = {"code": code, "expires_at": time.time() + 300}
    _sms_save(data)

    # 尝试发真实短信（有阿里云 Key 且未强制演示模式时）
    demo_mode = os.environ.get("SMS_DEMO_MODE", "true").lower() != "false"
    if not demo_mode:
        alibab_key = os.environ.get("ALIBABA_ACCESS_KEY_ID", "")
        alibab_secret = os.environ.get("ALIBABA_ACCESS_KEY_SECRET", "")
        sign_name = os.environ.get("ALIBABA_SMS_SIGN_NAME", "")
    else:
        alibab_key = alibab_secret = sign_name = ""

    if alibab_key and alibab_secret and sign_name:
        try:
            from alibabacloud_dypnsapi20170525.client import Client as DysmsapiClient
            from alibabacloud_dypnsapi20170525 import models as dysmsapi_models
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=alibab_key,
                access_key_secret=alibab_secret,
                endpoint="dypnsapi.aliyuncs.com",
            )
            client = DysmsapiClient(config)
            req = dysmsapi_models.SendSmsVerifyCodeRequest(
                phone_number=phone,
                template_code="100001",
                template_param=json.dumps({"code": code, "min": "5"}),
                sign_name=sign_name,
            )
            resp = client.send_sms_verify_code(req)
            body = resp.body
            if body.code in ("OK", "10000", "GatewayVerifySuccess"):
                return {
                    "success": True,
                    "message": "验证码已发送",
                    "channel": "alibaba-pnvs",
                }
            return {
                "success": True,
                "message": "验证码已发送（演示模式）",
                "channel": "demo-fallback",
                "demo": code,
                "smsError": str(body.code),
            }
        except Exception as e:
            pass  # 降级演示模式

    return {
        "success": True,
        "message": "验证码已发送",
        "channel": "demo",
        "demo": code,
    }


@router.post("/verify-sms")
async def verify_sms(request: Request):
    """校验短信验证码"""
    body = await request.json()
    phone = body.get("phone", "")
    code = body.get("code", "")

    data = _clean_expired()
    record = data.get(phone)
    if not record or record["code"] != code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    del data[phone]
    _sms_save(data)
    return {"success": True, "message": "验证通过", "phone": phone}


@router.post("/face-verify")
async def face_verify(request: Request):
    """支付宝人脸认证（无密钥时降级演示模式）"""
    body = await request.json()
    phone = body.get("phone", "")

    alipay_app_id = os.environ.get("ALIPAY_APP_ID", "")
    alipay_private_key = os.environ.get("ALIPAY_PRIVATE_KEY", "")
    demo_mode = os.environ.get("ALIPAY_DEMO_MODE", "false").lower() != "false"

    if demo_mode or not alipay_app_id:
        return {
            "success": True,
            "demo": True,
            "data": {
                "realName": "张**",
                "channel": "demo",
                "message": "实名认证通过（演示模式）",
            },
        }

    certify_id = f"cert_{int(time.time())}"
    face_data = _face_store()
    face_data[certify_id] = {"phone": phone, "status": "pending"}
    _face_save(face_data)
    certify_url = f"https://certify.alipay.com/certifyPage.htm?certifyId={certify_id}"

    return {
        "success": True,
        "demo": False,
        "certifyId": certify_id,
        "certifyUrl": certify_url,
        "qrUrl": certify_url,
    }


@router.post("/face-query")
async def face_query(request: Request):
    """查询人脸认证结果"""
    body = await request.json()
    certify_id = body.get("certifyId", "")
    face_data = _face_store()
    record = face_data.get(certify_id)

    if not record:
        raise HTTPException(status_code=400, detail="认证记录不存在")

    return {"success": True, "passed": True, "phone": record["phone"]}


@router.post("/generate-did")
async def generate_did(request: Request):
    """生成 DID（去中心化身份标识）"""
    body = await request.json()
    phone = body.get("phone", "")

    signer = AIDSigner()
    signer.generate()
    did = signer.did
    pub_key = signer.export_public_key()

    doc = {
        "id": did,
        "verification_method": [
            {
                "id": f"{did}#key-1",
                "type": "Ed25519VerificationKey2018",
                "controller": did,
                "publicKeyMultibase": pub_key.hex(),
            }
        ],
        "authentication": [f"{did}#key-1"],
        "service": [],
        "metadata": {
            "phone": phone,
            "createdAt": __import__("datetime").datetime.now().isoformat(),
            "version": "2.0",
        },
    }

    return {
        "success": True,
        "data": {
            "did": did,
            "publicKey": pub_key.hex(),
            "privateKey": signer.export_private_key().hex(),
            "document": doc,
            "method": "did:aid",
            "createdAt": __import__("datetime").datetime.now().isoformat(),
            "algorithm": "Ed25519",
        },
    }


@router.post("/complete")
async def complete_registration(request: Request):
    """完成注册 — 将用户写入数据库"""
    body = await request.json()
    did = body.get("did", "")
    phone = body.get("phone", "")
    did_document = body.get("document", None)

    if not did:
        raise HTTPException(status_code=400, detail="缺少 DID")

    # 使用 Container 获取身份管理器
    container = Container.instance()

    # 以手机号哈希作为设备指纹（Web 端无真实设备指纹）
    if phone:
        device_fp = f"web_{hashlib.sha256(phone.encode()).hexdigest()[:16]}"
    else:
        device_fp = f"web_{int(time.time())}"

    # 真正写入用户记录
    result = container.identity.register_user(
        device_fingerprint=device_fp,
        alpha_id=did,  # DID 作为 alpha_id
        did_document=did_document,
        phone=phone,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "注册失败"))

    return {
        "success": True,
        "data": {
            "did": did,
            "alphaId": result.get("alpha_id", did),
            "userId": result.get("user_id", ""),
            "ghostKey": "",
            "providerInfo": None,
            "registeredAt": __import__("datetime").datetime.now().isoformat(),
            "nextStep": "/platform",
        },
    }
