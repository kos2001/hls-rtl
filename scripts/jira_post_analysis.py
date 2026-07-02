#!/usr/bin/env python3
"""Post truthful, single-author technical root-cause analysis comments to the
LSI Jira project.

Honesty model: every comment is the comment author's own technical analysis of
the failure mode described in the issue summary — NOT a fabricated record of a
multi-person discussion that never happened. Comments are organized into
analytical sections ([증상], [가설], [계측], [근본원인], [완화], [검증]) so a
reader sees an investigation note, not invented people talking.

Auth: JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN from env or a .env file
(pass --env). Reads the project key from JIRA_PROJECT_KEY (default LSI).

Usage:
    python3 scripts/jira_post_analysis.py --env /path/.env --dry-run
    python3 scripts/jira_post_analysis.py --env /path/.env --issue LSI-7
    python3 scripts/jira_post_analysis.py --env /path/.env          # all issues

Idempotent: comments carry a hidden marker; issues already holding >= the
section count are skipped.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

MARKER = "​"  # zero-width space tag on every comment we author


# --------------------------------------------------------------------------
# Auth / HTTP
# --------------------------------------------------------------------------
def load_env(path: str | None) -> None:
    if not path or not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def cfg() -> tuple[str, str, str, str]:
    base = (os.environ.get("JIRA_BASE_URL") or "https://oseokkim2001.atlassian.net").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN", "")
    proj = os.environ.get("JIRA_PROJECT_KEY", "LSI")
    return base, email, token, proj


def api(method, base, path, email, token, body=None):
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode())
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read().decode()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {method} {path}: {e.read().decode(errors='replace')[:500]}")


def list_issues(base, email, token, proj):
    issues, token_next = [], None
    while True:
        path = (f"/rest/api/3/search/jql?jql={urllib.parse.quote(f'project={proj} ORDER BY created ASC')}"
                f"&maxResults=100&fields=summary,status")
        if token_next:
            path += f"&nextPageToken={token_next}"
        d = api("GET", base, path, email, token)
        issues.extend(d.get("issues", []))
        token_next = d.get("nextPageToken")
        if not token_next:
            break
    return issues


def existing_marked(base, email, token, key):
    d = api("GET", base, f"/rest/api/3/issue/{key}/comment?maxResults=100", email, token)
    return sum(1 for c in d.get("comments", []) if MARKER in json.dumps(c.get("body", {})))


def adf(text):
    blocks = [b for b in text.split("\n\n") if b.strip()]
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": b.strip()}]} for b in blocks]}


def post(base, email, token, key, text):
    api("POST", base, f"/rest/api/3/issue/{key}/comment", email, token, {"body": adf(text + MARKER)})


import urllib.parse  # noqa: E402  (after functions to keep header tidy)


# --------------------------------------------------------------------------
# Truthful technical analysis content, keyed by (component, failure mode).
# Each entry is a list of analysis sections — the author's own reasoning.
# --------------------------------------------------------------------------
def analysis_for(summary: str) -> list[str]:
    s = summary

    def has(*ks): return all(k in s for k in ks)

    # ---- PM9C3 NVMe ----
    if "PM9C3-NVMe" in s and ("timeout" in s or "link down" in s):
        return [
            "[증상] 고온 지속 쓰기 부하에서 NVMe 컨트롤러가 command timeout(보통 admin/IO completion 누락) 이후 PCIe link down으로 전이. 정상 온도/저부하에서는 재현되지 않는 점에서 thermal 의존성이 명확함.",
            "[1차 가설] thermal throttling 진입 시점에 컨트롤러 내부 클럭/전압 스케일링과 PCIe LTSSM 상태머신 간 타이밍 경합 가능성. throttle로 인해 백엔드(NAND program) 지연 → host의 IO completion timeout(기본 30s) 초과 → host abort → CTO(completion timeout) → link recovery 실패 시 down.",
            "[계측] 재현 시 (1) 컨트롤러 thermal sensor 로그와 throttle state 타임스탬프, (2) AER(Advanced Error Reporting)로 PCIe correctable/fatal 카운터, (3) NVMe SMART의 Composite Temperature / Thermal Management Temperature 1·2 transition, (4) LTSSM trace를 동시 캡처. timeout 직전 throttle 진입과 정렬되는지 확인.",
            "[근본원인 후보] (a) 펌웨어 throttle 진입 시 in-flight command를 abort하지 않고 무한 대기, (b) NAND program/erase suspend가 thermal 경로에서 누락되어 tPROG가 길어짐, (c) refclk SSC 또는 PLL relock이 고온에서 marginal. (a)·(b)는 펌웨어, (c)는 PHY/SI 이슈로 분리됨.",
            "[완화] 단기: host IO timeout 상향 또는 queue depth 축소로 throttle 구간 부하 평탄화. thermal threshold(TMT1/TMT2)를 낮춰 hard throttle 이전에 soft throttle로 진입. 중기: 펌웨어에서 throttle 진입 시 in-flight command graceful abort + completion 보장.",
            "[검증] 온도 챔버에서 throttle threshold 직상단 온도로 고정 후 sustained write(예: fio 128k seq, QD32) 장시간 구동하여 link down 0회 확인. AER fatal=0, CTO=0을 pass 기준으로. 수정 전/후 throttle 구간의 latency 분포(p99.9)를 비교해 회귀 가드로 보존.",
        ]
    if "PM9C3-NVMe" in s and ("UNC" in s or "uncorrectable" in s or "전원차단" in s):
        return [
            "[증상] 비정상 전원차단(ungraceful shutdown)을 반복한 뒤 특정 LBA 읽기에서 UNC(uncorrectable) 반환. 정상 종료 시퀀스에서는 미발생 → power-loss 경로의 데이터 무결성 문제.",
            "[1차 가설] PLP(power-loss protection)로 보호되는 write buffer/FTL 매핑 저널이 전원차단 시점에 완전히 비워지지 않음. 결과적으로 일부 LBA의 매핑이 partially-programmed page를 가리켜 ECC 복구 불가 → UNC.",
            "[계측] (1) PLP hold-up 커패시터 실제 hold 시간 측정(설계 마진 대비), (2) 전원차단 트리거 시점의 in-flight write 수와 flush 완료 여부, (3) 펌웨어 저널 replay 로그에서 미완료 트랜잭션 카운트, (4) UNC LBA가 최근 write LBA 집합과 겹치는지 상관분석.",
            "[근본원인 후보] (a) PLP hold-up 시간이 worst-case(고온·노화 커패시터)에서 전체 flush를 못 끝냄, (b) program-suspend 중이던 페이지가 차단으로 partial program 상태로 남음, (c) 저널 replay 순서 버그로 stale 매핑 채택. 노화 의존성이면 (a) 유력.",
            "[완화] flush 대상을 줄이도록 write buffer watermark 하향, atomic write 단위 축소. 펌웨어에서 power-loss 인터럽트 수신 시 program-suspend 페이지를 우선 abort/재기록 대상으로 마킹. 손상 LBA는 read 시 UNC 대신 deterministic zero 반환 정책 검토(스펙 합치 확인 필요).",
            "[검증] 전원차단 주입기로 write 한가운데 차단을 수천 사이클 반복하는 power-cycle 스트레스. 매 사이클 후 전체 LBA scrub read로 UNC=0 확인. 고온 + 노화 커패시터 조건을 worst-case로 포함. 통과 기준은 N회 반복 후 UNC 0건.",
        ]
    if "PM9C3-NVMe" in s and "TRIM" in s:
        return [
            "[증상] Deterministic TRIM(DRAT/RZAT 기대) 이후 해당 LBA 읽기가 0이 아닌 garbage 반환. 스펙상 deterministic read zero여야 하므로 명백한 데이터 정합성 위반.",
            "[1차 가설] TRIM(dataset management dealloc)이 FTL 매핑은 해제했으나 read 경로가 deallocated 매핑을 zero로 강제하지 않고 과거 물리 페이지를 그대로 읽음. 즉 dealloc 상태 비트와 read mux의 처리 불일치.",
            "[계측] TRIM 직후 (1) 해당 LBA의 매핑 엔트리 상태(valid/dealloc 비트), (2) read 경로가 dealloc일 때 zero-fill을 타는지 trace, (3) Identify Namespace의 DLFEAT(Deallocated Logical Block Features) 보고값과 실제 동작 일치 여부 확인.",
            "[근본원인 후보] (a) DLFEAT은 RZAT를 광고하나 펌웨어 read 경로에 zero-fill 분기 누락, (b) dealloc이 비동기로 적용되어 race window에 stale read, (c) GC가 dealloc 페이지를 재활용 전 read에서 노출. (a)면 광고/구현 불일치로 즉시 수정 대상.",
            "[완화] 단기: DLFEAT 광고를 실제 동작(non-deterministic)에 맞게 정정해 host 가정을 깨지 않게 함. 정식 수정: read 경로에서 dealloc 매핑은 항상 zero-fill. host 측은 TRIM 후 read-verify 의존 코드를 점검.",
            "[검증] write→TRIM→read 패턴을 다양한 LBA 정렬/크기로 반복하여 전부 zero 확인. GC 강제 트리거 후에도 동일. DLFEAT 보고값과 실측 동작을 자동 비교하는 회귀 케이스 추가.",
        ]

    # ---- UFS4 ----
    if "UFS4-Controller" in s and ("저온" in s or "startup" in s or "hang" in s):
        return [
            "[증상] 저온 부팅 시 UFS link startup(UniPro DME link startup) 실패로 부팅 hang. 상온 이상에서는 정상 → 저온에서 PHY/타이밍 마진 부족이 의심됨.",
            "[1차 가설] 저온에서 M-PHY의 PLL lock 시간 또는 RX equalizer 수렴이 느려져 DME_LINKSTARTUP 핸드셰이크가 timeout. 또는 저온에서 reference clock 안정화 시간이 부팅 시퀀스의 link-up 윈도우를 초과.",
            "[계측] (1) 부팅 시 UniPro link startup 시도 횟수와 실패 attribute(PA_*), (2) M-PHY PLL lock done 타이밍 vs 시도 시점, (3) 저온에서 refclk ready→link-up 시도 간격, (4) HS-GEAR fallback 발생 여부(저온에서 PWM/HS-G1로 자동 강등되는지).",
            "[근본원인 후보] (a) link startup retry 횟수/타임아웃이 저온 worst-case에 부족, (b) PHY calibration 값이 저온에서 미보정(온도 보상 LUT 누락), (c) power-up 시퀀스에서 PHY ready 폴링 없이 고정 지연 사용. (a)·(c)는 펌웨어/부트, (b)는 PHY 캘리브레이션.",
            "[완화] 부팅 시 link startup retry 횟수 상향 및 초기 gear를 보수적으로 시작 후 단계적 상향. PHY power-up 후 PLL lock done을 폴링하도록 고정 지연 제거. 저온 온도 보상 캘리브레이션 적용.",
            "[검증] 저온 챔버(스펙 하한, 예 -30~-40°C)에서 cold-boot 수백 회 반복하여 link-up 100% 성공 확인. link startup 소요 시간 분포를 로깅해 마진 확보 여부 정량화.",
        ]
    if "UFS4-Controller" in s and ("latency spike" in s or "버스트" in s or "카메라" in s):
        return [
            "[증상] 고부하 카메라 버스트 촬영 중 UFS write latency가 간헐적으로 >500ms로 spike. 평상시 정상이나 대량 연속 write에서 tail latency 폭증.",
            "[1차 가설] 버스트 write가 SLC 캐시(write booster/turbo write) 용량을 소진하면 직접 TLC program 또는 background GC와 경합. host write가 GC/캐시 flush 뒤로 밀리며 tail latency 발생.",
            "[계측] (1) write latency 분포(p50/p99/p99.9)와 spike 시점의 누적 write 양 상관, (2) write booster buffer 잔량과 flush 이벤트, (3) GC 활성 구간과 spike 정렬, (4) HS-GEAR/clock scaling이 부하 중 강등되는지.",
            "[근본원인 후보] (a) write booster 버퍼 고갈 후 direct TLC fallback, (b) GC가 foreground write를 충분히 양보하지 않음(우선순위/스로틀 정책), (c) thermal로 인한 clock gear 강등이 부하 중 발생. 촬영 버스트 길이 의존이면 (a) 유력.",
            "[완화] write booster buffer 크기/소진 정책 조정, host 측 카메라 파이프라인에 write 평탄화(ring buffer + 백그라운드 flush). GC 스로틀을 foreground 우선으로 튜닝. 필요 시 turbo write 영구 모드 검토(수명 트레이드오프 고려).",
            "[검증] 카메라 버스트 시나리오를 fio로 모사(대용량 연속 write 후 idle 반복)하여 p99.9 latency가 목표(예 <100ms) 이내인지 확인. 수정 전/후 tail latency 회귀 비교.",
        ]

    # ---- ISOCELL-HP9 image sensor ----
    if "ISOCELL-HP9" in s and ("banding" in s or "줄무늬" in s):
        return [
            "[증상] 특정 조도에서 horizontal banding(가로 줄무늬) noise. 조도 의존성이 있으므로 노출/아날로그 게인 또는 row 단위 노이즈와 연관 가능성.",
            "[1차 가설] row-wise 고정 패턴 노이즈(FPN) 또는 row driver/ADC ramp의 전원 노이즈가 특정 게인에서 두드러짐. 또는 LED 조명과의 flicker 비트(rolling shutter × 광원 주파수) 가능성.",
            "[계측] (1) banding 주기를 row 단위로 측정(고정 row 간격인지 시간 가변인지), (2) 발생 조도/노출/게인 조합 매핑, (3) 광원 종류(자연광 vs 50/60Hz LED) 의존성, (4) dark frame에서도 재현되는지(센서 내부 vs 광원).",
            "[근본원인 후보] (a) row driver 전원(AVDD) ripple이 ADC ramp에 커플링, (b) row-wise FPN 보정(black level / row-noise correction) 미흡, (c) 광원 flicker와 rolling shutter 비트. dark frame 재현이면 (a)·(b), 광원 의존이면 (c).",
            "[완화] 전원 디커플링/LDO 분리로 row driver 노이즈 저감, on-sensor row-noise correction 강도 조정. flicker면 anti-banding(노출을 광원 주기 정수배로) 적용. 센서 보정 LUT 재캘리브레이션.",
            "[검증] 균일 조명 차트에서 조도/게인 스윕하며 banding 진폭(라인 프로파일 표준편차)을 정량 측정, 목표 임계 이하 확인. dark/light 양쪽, 50/60Hz 광원 모두 포함한 매트릭스 회귀.",
        ]
    if "ISOCELL-HP9" in s and ("HDR" in s or "ghosting" in s or "motion" in s):
        return [
            "[증상] HDR 모드에서 움직이는 피사체에 motion artifact(ghosting). 정지 장면은 정상 → 다중 노출 HDR 합성의 시간차가 원인일 가능성이 큼.",
            "[1차 가설] staggered HDR(장/단 노출 시간차)에서 노출 간 피사체 이동으로 합성 시 ghost. de-ghosting(motion detection 기반 가중) 로직의 임계가 빠른 움직임을 못 따라감.",
            "[계측] (1) 장/단 노출 시간차(Δt)와 ghost 심각도 상관, (2) de-ghost 모듈의 motion map 출력 확인, (3) DCG/staggered 모드별 재현 차이, (4) 피사체 속도(픽셀/프레임) 임계 측정.",
            "[근본원인 후보] (a) 노출 간 Δt가 과도(라인 인터리브 타이밍), (b) de-ghosting motion threshold가 보수적이라 ghost 영역을 단노출로 대체 못함, (c) 합성 가중이 saturation 경계에서 불연속. (a)면 센서 타이밍, (b)·(c)면 ISP 합성.",
            "[완화] staggered Δt 단축(가능하면 DCG 등 동시성 높은 HDR 모드 사용), de-ghosting threshold를 움직임 영역에서 단노출 우선으로 조정, 합성 가중 함수 평활화.",
            "[검증] 모션 차트(회전 디스크/이동 막대)로 다양한 속도에서 ghost 가시성 정량화, 목표 이하 확인. 정지/저속/고속 및 HDR 모드별 매트릭스로 회귀.",
        ]

    # ---- MDM-5400 modem ----
    if "MDM-5400" in s and ("RRC" in s or "핸드오버" in s or "handover" in s):
        return [
            "[증상] NSA→SA 핸드오버(또는 그 역) 중 간헐적 RRC connection drop. 정적 셀에서는 안정, 전이 구간에서만 발생 → 핸드오버 시그널링/타이밍 경합 의심.",
            "[1차 가설] NSA→SA 전환 시 측정 보고/RRC reconfiguration 타이밍과 lower layer 재설정(베어러 재맵핑)의 경합으로 reconfiguration complete 누락 → T304 만료 → RLF.",
            "[계측] (1) 드롭 시점의 RRC 메시지 시퀀스(reconfiguration / complete / RLF), (2) T304/T310 타이머 만료 여부, (3) 측정 보고 트리거(A3/A5) 임계와 실제 RSRP/RSRQ, (4) UE↔네트워크 capability 협상 로그.",
            "[근본원인 후보] (a) reconfiguration 처리 지연으로 T304 만료, (b) 측정 이벤트 임계/히스테리시스가 전이 구간에서 핑퐁 유발, (c) SA capability 협상 불일치로 재설정 실패. 특정 셀 페어에서 재현되면 (b) 가능성.",
            "[완화] 측정 이벤트 히스테리시스/TTT(time-to-trigger) 조정으로 핑퐁 억제, reconfiguration 처리 경로 지연 단축, capability 협상 케이스 보강. 필요 시 conditional handover(CHO) 활용.",
            "[검증] 콘덕티드/필드에서 NSA↔SA 전이를 반복 유발하는 시나리오로 drop rate 측정, 목표(예 <0.1%) 이하 확인. RLF 카운터와 T304 만료 0 지향. 회귀를 위해 시그널링 트레이스 자동 파싱.",
        ]
    if "MDM-5400" in s and ("mmWave" in s or "빔" in s or "throughput" in s):
        return [
            "[증상] mmWave 빔 트래킹 실패로 throughput 급락 후 회복 지연. blockage/이동 시 빔 재획득이 느려 사용자 체감 stall 발생.",
            "[1차 가설] beam failure detection(BFD) 후 beam failure recovery(BFR) 절차의 후보 빔 셋이 부족하거나 RACH 기반 복구 지연. 또는 L1-RSRP 보고 주기가 빠른 blockage를 못 따라감.",
            "[계측] (1) BFD 트리거→BFR 완료 소요 시간, (2) 후보 빔(candidate beam) 수와 품질, (3) CSI-RS/SSB 빔 측정 주기, (4) blockage 이벤트와 throughput 급락 정렬.",
            "[근본원인 후보] (a) BFR 후보 빔 풀이 작아 적합 빔 부재 시 RACH fallback 지연, (b) 빔 측정/보고 주기 과대, (c) MAC의 BFR 우선순위 부족. 이동/회전 시 재현이면 (b) 유력.",
            "[완화] 빔 측정 주기 단축 및 후보 빔 셋 확대, BFR을 우선 스케줄링, panel/빔 다양성 활용. 상위에서 mmWave→sub-6 빠른 fallback로 throughput 바닥 방지.",
            "[검증] 빔 blockage를 주기적으로 유발(차폐/회전)하며 throughput 회복 시간(급락→90% 회복)을 측정, 목표 이하 확인. BFR 성공률과 RACH fallback 비율을 회귀 지표로.",
        ]

    # ---- DDI-OLED-T7 display driver ----
    if "DDI-OLED-T7" in s and ("VRR" in s or "flicker" in s or "깜빡임" in s):
        return [
            "[증상] 가변주사율(VRR) 전환 시 화면 깜빡임(flicker). 고정 주사율에서는 미발생 → refresh rate 전이 시 휘도/타이밍 불연속이 원인.",
            "[1차 가설] VRR로 frame time이 바뀔 때 OLED 화소의 발광 시간/감마 보정이 새 주사율에 맞게 갱신되지 않아 평균 휘도가 프레임 간 불연속 → flicker 인지. 특히 저주사율에서 leakage로 휘도 강하.",
            "[계측] (1) 전환 전후 frame time과 emission duty, (2) 주사율별 감마/휘도 캘리브레이션 적용 여부, (3) 저주사율에서 화소 전압 droop(휘도 강하) 측정, (4) flicker 주파수와 전환 이벤트 정렬.",
            "[근본원인 후보] (a) 주사율별 감마/휘도 보정 LUT 미전환 또는 전환 지연, (b) 저주사율 leakage 보상(예 화소 리프레시) 부족, (c) 전환 시 1프레임 타이밍 글리치. (a)·(b)는 DDI 보정, (c)는 타이밍.",
            "[완화] 주사율별 감마/휘도 LUT를 전환 프레임에 글리치 없이 적용(double-buffering), 저주사율 leakage 보상 강화, 전환을 점진적(주사율 ramp)으로.",
            "[검증] 광계측기로 VRR 전환 구간 휘도 시계열을 측정해 flicker(JEITA/percent flicker, 휘도 변동률)를 정량화, 인지 임계 이하 확인. 다양한 전환 쌍(예 120→48, 60→120) 매트릭스 회귀.",
        ]
    if "DDI-OLED-T7" in s and ("color mura" in s or "색온도" in s or "접힘" in s):
        return [
            "[증상] 폴더블 패널 접힘부 경계에서 색온도 불일치(color mura). 평탄 영역은 균일하나 접힘부에서 색/휘도 불균일 → 기구 응력 또는 영역별 보정 경계 문제.",
            "[1차 가설] 접힘부의 기계적 응력/곡률로 OLED 발광 특성이 변하거나, demura/색보정 캘리브레이션이 접힘부 경계에서 보간 불연속을 만듦.",
            "[계측] (1) 접힘부 vs 평탄부의 색좌표(CIE x,y)·휘도 프로파일, (2) demura 보정맵의 경계 처리 방식, (3) 접힘 횟수(노화)에 따른 mura 진행, (4) 곡률 반경과 색편차 상관.",
            "[근본원인 후보] (a) demura 캘리브레이션이 접힘부 곡률을 반영 못함, (b) 보정맵 영역 분할 경계의 보간 불연속, (c) 기구 응력에 의한 패널 자체 특성 변화(노화 가속). (b)는 알고리즘, (a)·(c)는 캘리브레이션/패널.",
            "[완화] demura 보정맵을 접힘부 곡률 포함해 재캘리브레이션, 경계 보간을 평활화, 노화 보상(접힘 사이클 기반) 추가 검토.",
            "[검증] 접힘 각도별·노화 사이클별로 접힘부 색좌표 편차(ΔE)와 휘도 균일도를 측정, 목표(ΔE 임계) 이하 확인. 접힘 내구 시험과 연계한 장기 회귀.",
        ]

    # ---- PMIC-S2MPS27 ----
    if "PMIC-S2MPS27" in s and ("undershoot" in s or "transient" in s or "AP reset" in s):
        return [
            "[증상] 부하 급변(load transient) 시 코어 레일 undershoot로 AP reset. 정상 부하에서는 안정, 급격한 부하 step에서만 발생 → 레귤레이터 transient 응답 마진 부족.",
            "[1차 가설] 코어 레일 buck의 transient 응답(슬루율/대역폭)이 AP의 빠른 부하 step을 못 따라가 undershoot가 PMIC/AP의 UVLO 또는 reset 임계 하회.",
            "[계측] (1) load step 시 레일 전압 파형(undershoot 깊이/지속), (2) DVS 전압과 reset 임계의 마진, (3) 출력 커패시턴스/ESR, (4) AP 부하 step 크기·슬루율과 undershoot 상관.",
            "[근본원인 후보] (a) buck 보상/대역폭 부족, (b) 출력 커패시터 용량/배치 부족, (c) DVS 설정 전압이 reset 임계에 너무 근접해 마진 부족, (d) AP의 부하 step 자체가 과도. (c)는 설정으로 즉시 완화 가능.",
            "[완화] 코어 레일 DVS floor 상향으로 reset 임계 마진 확보, buck transient 응답 모드(예 PWM 강제/auto) 조정, 출력 디커플링 보강, AP 측 부하 step 평탄화(클럭 ramp).",
            "[검증] 부하 step 제너레이터로 최악 slew·step에서 undershoot 깊이를 측정, reset 임계 대비 마진(예 >50mV) 확보 확인. 온도/공정 코너 포함. 수정 전/후 마진 회귀 비교.",
        ]
    if "PMIC-S2MPS27" in s and ("NACK" in s or "I2C" in s or "SPMI" in s):
        return [
            "[증상] I2C/SPMI 버스 통신 중 간헐적 NACK로 레일 설정 누락. 누락 시 의도한 전압/시퀀스가 적용 안 됨 → 하위 블록 오동작 위험.",
            "[1차 가설] 버스 신호 무결성(상승시간/터미네이션) 또는 다중 마스터/클럭 스트레칭 경합으로 간헐 NACK. NACK 후 재시도 로직 부재로 설정이 영구 누락.",
            "[계측] (1) NACK 발생 시 버스 파형(SCL/SDA 상승시간, 글리치), (2) NACK 직전 트랜잭션 패턴과 버스 점유율, (3) 클럭 스트레칭/arbitration loss 여부, (4) 누락된 레지스터와 후속 영향.",
            "[근본원인 후보] (a) pull-up/용량성 부하로 상승시간 위반, (b) SPMI arbitration 또는 I2C 다중 마스터 경합, (c) 슬레이브 클럭 스트레칭 미지원으로 타이밍 위반, (d) 드라이버에 NACK 재시도 누락. (d)는 즉시 가드 추가 가능.",
            "[완화] 드라이버에 NACK 시 bounded 재시도 + 실패 시 명시적 에러 처리 추가(설정 silently drop 금지), 버스 pull-up/속도 재튜닝, arbitration 정책 점검.",
            "[검증] 버스 부하/노이즈 주입 환경에서 대량 레일 설정 트랜잭션 반복하여 NACK 후 최종 레지스터 값이 항상 의도대로인지 read-back 검증. NACK율과 누락 0건을 pass 기준으로.",
        ]

    # ---- NPU-EdgeX2 ----
    if "NPU-EdgeX2" in s and ("비결정성" in s or "non-deterministic" in s or "양자화" in s):
        return [
            "[증상] 특정 양자화 모델에서 추론 결과 비결정성(동일 입력에 상이 출력). FP 모델/타 모델은 결정적 → 양자화 경로 또는 병렬 누산 순서 의존 의심.",
            "[1차 가설] 멀티코어/타일 분할 시 부분합 누산 순서가 런타임에 따라 달라져 양자화 반올림 차이 누적. 또는 requantization 스케일/zero-point 계산에 race나 미초기화 존재.",
            "[계측] (1) 동일 입력 반복 추론의 비트 차이 위치/빈도, (2) 단일코어 강제 시 재현 여부, (3) 누산 정밀도(int32 누산 vs 중간 양자화), (4) 타일/스케줄 분할이 결과에 영향 주는지.",
            "[근본원인 후보] (a) 부동/정수 누산 순서 비결정으로 반올림 발산, (b) requant 파라미터의 race/미초기화 메모리, (c) DMA double-buffer 동기화 누락으로 stale weight/activation. 단일코어에서 사라지면 (a)·(c).",
            "[완화] 누산 순서 고정(결정적 reduction tree), int32 full-precision 누산 후 단일 requant, double-buffer 동기화 배리어 추가, 미초기화 버퍼 제거.",
            "[검증] 동일 입력 N회 추론 결과가 비트 일치하는지 자동 검사(여러 코어 수/스케줄에서). 결정성 회귀 케이스를 CI에 추가해 재발 시 즉시 검출.",
        ]
    if "NPU-EdgeX2" in s and ("DMA" in s or "descriptor" in s or "로드" in s):
        return [
            "[증상] 대형 모델 로드 시 DMA descriptor 부족으로 추론 실패. 소형 모델은 정상 → descriptor 풀 용량/관리가 모델 크기를 못 받쳐줌.",
            "[1차 가설] 정적 할당된 DMA descriptor 링이 대형 모델의 weight/activation 전송 수를 초과. 또는 descriptor 재활용/완료 회수가 늦어 고갈.",
            "[계측] (1) 모델별 필요한 descriptor 수 vs 풀 크기, (2) 실패 시점의 descriptor in-use/free 카운트, (3) 완료 인터럽트/회수 지연, (4) 단편화로 연속 descriptor 부족 여부.",
            "[근본원인 후보] (a) descriptor 풀 정적 크기 부족, (b) 완료된 descriptor 회수 지연으로 free 부족, (c) 단편화. (a)면 크기 산정 버그, (b)면 회수 경로 문제.",
            "[완화] descriptor 풀을 모델 worst-case 기반으로 동적/충분히 할당, 전송을 청크 분할(스트리밍 로드)로 동시 descriptor 수 상한, 완료 회수 경로 지연 단축.",
            "[검증] 최대 지원 모델 크기로 로드/추론 반복하여 descriptor 고갈 0건 확인. 풀 사용률 high-watermark를 로깅해 마진 정량화. 경계 모델 크기 회귀 케이스 추가.",
        ]

    # ---- LPDDR5X-PHY ----
    if "LPDDR5X-PHY" in s and ("비트 에러" in s or "8533" in s or "온도" in s):
        return [
            "[증상] 최고속(8533Mbps) 동작 시 특정 온도에서 비트 에러 상승. 저속/타 온도에서는 정상 → 고속 타이밍 마진의 온도 의존성 문제.",
            "[1차 가설] 온도 변화로 DRAM/PHY의 타이밍이 drift했으나 주기적 retraining(또는 온도 보상)이 충분치 않아 read/write eye가 닫힘. DQ/DQS 정렬 또는 Vref 마진 부족.",
            "[계측] (1) 온도 스윕하며 read/write eye margin(타이밍/전압) 측정, (2) periodic retraining 주기와 온도 변화율 비교, (3) per-byte-lane 에러 분포, (4) Vref/DFE 설정의 온도별 적정성.",
            "[근본원인 후보] (a) 온도 보상 retraining 주기 과대로 drift 누적, (b) 특정 lane의 SI 마진 부족(레이아웃), (c) Vref/eq 캘리브레이션이 해당 온도 코너 미반영. 특정 lane 집중이면 (b).",
            "[완화] 온도 기반 retraining 트리거 강화(ΔT 임계 하향), 해당 온도 코너용 Vref/DFE 재캘리브레이션, 필요 시 마진 부족 구간 gear 다운. 장기적으로 SI 레이아웃 검토.",
            "[검증] 온도 챔버에서 코너 온도 고정 후 고속 메모리 BIST/스트레스(march, 랜덤)로 BER 측정, 목표(예 무에러 또는 ECC 보정 가능 범위) 확인. 온도 ramp 중 retraining 효과도 검증.",
        ]
    if "LPDDR5X-PHY" in s and ("self-refresh" in s or "training" in s):
        return [
            "[증상] self-refresh 진입/탈출 시 드문 training 실패로 hang. 정상 동작 중에는 안정, SR 전이에서만 간헐 → 전이 시퀀스/재training 경합 의심.",
            "[1차 가설] SR 탈출 후 short retraining(또는 ZQ calibration) 결과가 간헐적으로 수렴 실패하거나, 전이 중 클럭/CKE 시퀀스 타이밍 위반으로 컨트롤러가 hang.",
            "[계측] (1) SR enter/exit 시퀀스 신호(CKE, CK, retraining 트리거) 타이밍, (2) 실패 시 retraining 수렴 상태/코드, (3) ZQ cal 타이밍, (4) 전이 직후 첫 access의 마진.",
            "[근본원인 후보] (a) SR exit 후 retraining 미수행/불충분으로 drift된 타이밍 사용, (b) 전이 시퀀스 타이밍 위반(tXSR 등), (c) retraining 알고리즘이 특정 조건에서 비수렴. (b)면 컨트롤러 시퀀스, (c)면 알고리즘.",
            "[완화] SR exit 시 retraining/ZQ를 항상 수행하도록 보장, 전이 타이밍 파라미터(tXSR 등) 마진 확보, retraining 비수렴 시 안전 fallback(재시도/gear 다운).",
            "[검증] SR enter/exit를 다양한 idle 길이/온도에서 수만 회 반복하여 hang/training 실패 0건 확인. 전이 직후 access 마진을 로깅해 회귀 가드로.",
        ]

    # ---- AUTO-MCU-V9 ----
    if "AUTO-MCU-V9" in s and ("CAN-FD" in s or "프레임 손실" in s):
        return [
            "[증상] CAN-FD 고부하 버스트에서 간헐적 프레임 손실. 저부하는 정상 → RX 처리량/버퍼 또는 중재 손실 누적 문제.",
            "[1차 가설] 버스트 시 RX FIFO/메일박스가 ISR 처리 속도를 초과해 overrun, 또는 우선순위 낮은 프레임의 arbitration 반복 손실로 지연/폐기.",
            "[계측] (1) 손실 시점의 RX FIFO overrun 카운터, (2) ISR/DMA 처리 지연과 버스 부하율, (3) 손실 프레임의 ID 우선순위 분포, (4) error counter(REC/TEC)와 bus-off 근접 여부.",
            "[근본원인 후보] (a) RX 버퍼 깊이 부족 + ISR 지연으로 overrun, (b) DMA 미사용으로 per-frame 인터럽트 과부하, (c) 저우선 ID의 arbitration starvation. (a)·(b)는 처리경로, (c)는 메시지 설계.",
            "[완화] RX FIFO/DMA 활용으로 per-frame ISR 부하 제거, 버퍼 깊이 상향, 우선순위/주기 재배치로 starvation 완화. 필요 시 버스 부하율 상한 정책.",
            "[검증] 버스 부하를 포화 근처까지 올린 버스트 시나리오에서 프레임 손실 0, overrun 0 확인. REC/TEC 안정 유지. 부하율별 손실률을 회귀 지표로.",
        ]
    if "AUTO-MCU-V9" in s and ("lockstep" in s or "ASIL" in s or "safety trap" in s):
        return [
            "[증상] ASIL-D lockstep 코어 간 transient 불일치로 false safety trap(실제 영구결함 아님). 안전 메커니즘이 일시적 불일치를 영구결함으로 오판해 불필요한 trap.",
            "[1차 가설] 두 코어 입력 동기(클럭/리셋 위상, 입력 정렬) 미세 차이 또는 SEU성 transient가 비교기에 잡혀 mismatch. 비교 윈도우/필터가 일시 glitch를 허용 안 함.",
            "[계측] (1) mismatch 발생 시 두 코어 신호 위상차, (2) transient의 재현성(영구 vs 일시), (3) 입력 동기화 경로 마진, (4) 비교기 타이밍/필터 설정.",
            "[근본원인 후보] (a) 코어 간 입력/클럭 스큐로 비교 타이밍 마진 부족, (b) SEU성 single-event transient, (c) 비교기 필터가 1-cycle glitch도 영구결함으로 분류. (a)·(c)면 설계 마진/정책, (b)면 환경.",
            "[완화] 입력 동기화 마진 확보(스큐 보정), 비교 결과에 대한 짧은 glitch 필터/재확인 후 trap(안전 요구사항 범위 내에서), SEU 대비 ECC/재시도 적용. 단, 안전 목표(diagnostic coverage) 훼손 없는 선에서 설계.",
            "[검증] 입력 스큐/노이즈를 코너로 주입하며 false trap율 측정, 영구결함 주입 시 검출(true positive)은 100% 유지 확인. 안전 분석(FMEDA) 영향 재평가.",
        ]

    # ---- SE-Secure7 ----
    if "SE-Secure7" in s and ("APDU" in s or "NFC" in s or "timeout" in s):
        return [
            "[증상] NFC 동시 동작 중 eSE APDU 응답 timeout. eSE 단독은 정상, NFC 동시 동작에서만 → 자원/버스 경합 또는 RF 간섭 의심.",
            "[1차 가설] eSE와 NFC controller가 공유하는 인터페이스(예 SWP/SPI/I2C) 또는 전원 경합으로 APDU 처리가 지연되어 host timeout. 또는 RF 필드 중 eSE 전류 변동.",
            "[계측] (1) timeout 시 eSE↔host 인터페이스 트래픽과 NFC 활동 정렬, (2) 공유 버스/전원 경합 여부, (3) APDU 처리 지연 분포, (4) RF 필드 강도와 timeout 상관.",
            "[근본원인 후보] (a) 공유 인터페이스 중재로 APDU 지연, (b) NFC RF 동작 중 eSE 전원 droop, (c) host APDU timeout이 동시 동작 worst-case 대비 짧음. (c)면 설정으로 즉시 완화.",
            "[완화] APDU timeout을 동시 동작 worst-case 기준으로 상향, 공유 인터페이스 중재/우선순위 조정, eSE 전원 디커플링 보강, 동시 동작 시 처리 스케줄 분리.",
            "[검증] NFC 트랜잭션과 eSE APDU를 동시 부하로 반복하여 timeout 0건 확인. 다양한 RF 필드/거리에서 APDU 지연 분포를 측정해 마진 확보.",
        ]
    if "SE-Secure7" in s and ("glitch" in s or "attestation" in s or "보안 부팅" in s):
        return [
            "[증상] 전압 glitch 환경에서 보안 부팅 측정값(attestation) 불일치. 정상 전원에서는 일치, glitch 주입 시 측정값 변동 → fault 주입에 대한 측정 경로 견고성 문제.",
            "[1차 가설] glitch가 측정(해시) 계산 또는 측정값 기록 경로의 일부 연산을 건너뛰게/오염시켜 PCR/attestation 값이 변함. fault detection이 해당 구간을 못 잡음.",
            "[계측] (1) glitch 타이밍 스윕과 불일치 발생 구간 매핑, (2) 측정 해시 계산 단계별 중간값, (3) glitch 검출 센서(전압 모니터) 동작 여부, (4) 불일치가 특정 부팅 단계에 집중되는지.",
            "[근본원인 후보] (a) 측정 연산에 fault 대비 중복/검증 부재(단일 계산), (b) glitch 센서 임계/응답 시간 부족, (c) 측정값 기록의 비원자적 갱신. 보안 관점에서 모두 강건성 강화 대상.",
            "[완화] 측정 연산의 중복 계산/결과 비교(fault-resistant), glitch 센서 임계·응답 강화, 측정값 기록을 원자적·검증된 경로로. 불일치 검출 시 안전 상태(부팅 중단)로.",
            "[검증] 전압 glitch 주입기로 타이밍/강도 스윕하며 (1) 잘못된 측정값이 attestation을 통과하지 못함(보안), (2) 정상 부팅 false reject 최소화를 동시 확인. fault 캠페인 커버리지를 회귀로 관리.",
        ]

    # ---- fallback (generic but still truthful: methodology, not invented facts) ----
    return [
        "[증상] 이슈 요약 기준으로 재현 조건(부하/온도/시퀀스 등)을 먼저 명확히 고정해야 함. 간헐 발생이면 트리거 조건을 좁히는 것이 우선.",
        "[접근] 가설 기반 디버깅: 증상에서 가능한 근본 원인 후보를 나열하고, 각 후보를 구분할 수 있는 계측(로그/파형/카운터)을 설계해 하나씩 배제.",
        "[계측] 발생 시점의 관련 상태(타이밍, 전원, 에러 카운터, 시퀀스 로그)를 동시 캡처해 증상과 정렬되는 신호를 식별.",
        "[완화] 근본 원인 확정 전에는 마진 확보(타임아웃/임계/재시도)로 영향 완화하되, silently drop이나 검증 우회는 금지.",
        "[검증] 수정 후 worst-case 코너에서 반복 스트레스로 재발 0 확인하고, 동일 증상을 잡는 회귀 케이스를 추가해 재발 방지.",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=None, help="path to .env with JIRA_* keys")
    ap.add_argument("--issue", default=None, help="restrict to one issue key")
    ap.add_argument("--limit", type=int, default=None, help="max issues to process")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    load_env(args.env)
    base, email, token, proj = cfg()
    if not args.dry_run and (not email or not token):
        sys.exit("Missing JIRA_EMAIL / JIRA_API_TOKEN (use --env or environment).")

    if not args.dry_run:
        me = api("GET", base, "/rest/api/3/myself", email, token)
        print(f"authenticated as {me.get('displayName')} <{me.get('emailAddress')}>")

    if args.issue:
        d = api("GET", base, f"/rest/api/3/issue/{args.issue}?fields=summary", email, token) if not args.dry_run else None
        summ = d["fields"]["summary"] if d else args.issue
        issues = [{"key": args.issue, "fields": {"summary": summ}}]
    elif args.dry_run:
        issues = [
            {"key": "LSI-7", "fields": {"summary": "[PM9C3-NVMe] 비정상 전원차단 반복 후 일부 LBA에서 UNC(uncorrectable) 에러"}},
            {"key": "LSI-9", "fields": {"summary": "[UFS4-Controller] 저온 부팅 시 UFS link startup 실패로 부팅 행(hang)"}},
        ]
    else:
        issues = list_issues(base, email, token, proj)
        print(f"found {len(issues)} issue(s) in {proj}")

    if args.limit:
        issues = issues[:args.limit]

    total = 0
    for iss in issues:
        key = iss["key"]
        summ = iss.get("fields", {}).get("summary", "")
        comments = analysis_for(summ)
        if not args.dry_run:
            have = existing_marked(base, email, token, key)
            if have >= len(comments):
                print(f"  {key}: already has {have} analysis comments, skipping")
                continue
        print(f"  {key} [{summ[:60]}]: {len(comments)} comments" + (" (dry-run)" if args.dry_run else ""))
        for n, c in enumerate(comments, 1):
            if args.dry_run:
                print(f"    [{n}] {c[:100]}{'...' if len(c) > 100 else ''}")
            else:
                post(base, email, token, key, c)
                time.sleep(args.delay)
            total += 1

    print(f"\n{'(dry-run) would post' if args.dry_run else 'posted'} {total} comments across {len(issues)} issue(s)")


if __name__ == "__main__":
    main()
