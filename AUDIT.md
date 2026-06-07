# Yemoda — Auditoría completa (multi-agente)

> Generada por una auditoría multi-agente (70 agentes, verificación adversarial). Hallazgos verificados contra el código fuente. **83 hallazgos brutos → 79 tras eliminar falsos positivos.**
>
> **Conteo:** 🔴 3 críticos · 🟠 12 altos · 🟡 13 medios · ⚪ 18 bajos.

## Resumen ejecutivo
SaaS de gestión Kanban (Django+DRF, FastAPI+Anthropic sobre un Postgres compartido, React+TS). Monetización = medición de IA per-proyecto + Stripe. La auditoría encontró que **los dos controles de los que depende el negocio —entitlement de cobro y medición de IA— son evadibles**, y el servicio de IA tiene un defecto de throughput/costo. Además: sin paginación en DRF + N+1 recursivo → list endpoints sin límite; el frontend descarga tablas globales y filtra en cliente; el cobro per-proyecto se reconcilia con flags a nivel usuario (PaymentSuccess queda "pending" para siempre; cancelar un proyecto Pro baja el premium de un usuario con dos), y no hay handler `customer.subscription.updated`.

---

## 🔴 Críticos

### C1. `/chat` de FastAPI sin auth y sin medición cuando falta project_id → Claude ilimitado gratis
`backend_fastapi/app/routers/chat.py` (router prefix sin `dependencies=`; `chat()` solo mide si `resolve_project_id()` no es None).
**Impacto:** cualquiera puede mandar prompts (opus, max_tokens alto) facturados a `ANTHROPIC_API_KEY`. Denial-of-wallet + se rompe el control de monetización.
**Fix:** `APIRouter(prefix="/chat", dependencies=[Depends(require_internal_token)])`; si `resolve_project_id()` es None → 400/402; Django reenvía un `project_id` verificado por membresía.

### C2. Mass-assignment: cualquier usuario puede crear proyecto con `plan="pro"`
`backend_django/apps/core/serializers.py` (`ProjectSerializer` usa `fields="__all__"`; `plan` y `stripe_subscription_id` escribibles).
**Impacto:** `POST /api/projects/ {"plan":"pro"}` → entitlements Pro gratis; corromper `stripe_subscription_id`.
**Fix (1 línea):** `read_only_fields = ("id_project","plan","stripe_subscription_id","created_by","created_at")`.

### C3. El review por push bloquea el event loop (SDK Anthropic sync en `async def`)
`backend_fastapi/app/routers/webhook.py` (`_process_push` `async def` en background_task → `anthropic.messages.create` bloqueante).
**Impacto:** cada push congela TODO el proceso varios segundos.
**Fix:** `_process_push` → `def` plano (threadpool) o `anyio.to_thread.run_sync`; no retener sesión de BD durante la llamada.

---

## 🟠 Altos

### Rendimiento
- **Sin paginación DRF + N+1 recursivo de subtareas** — `config/settings.py` (sin `DEFAULT_PAGINATION_CLASS`); `serializers.py` `rolled_up_points`. Fix: `LimitOffsetPagination` PAGE_SIZE 50-100; rollups en BD/in-memory.
- **Alta/baja de miembros: Stripe + GitHub bloqueantes en el request** — `views.py` `_sync_project_subscription_seats` + loop `_add_github_collaborator` (`timeout=20s`/repo). Fix: `transaction.on_commit` + background.
- **Frontend descarga tablas globales y filtra en cliente** — `useProjectData.ts` (`/tasks/` sin scope/paginación), Dashboard/Reports/Alerts; `handleRemoveMember` 1 request/tarea (N+1). Fix: scope+paginación server-side; endpoints agregados.

### Seguridad
- **`GithubAppLinkInstallationView` permite secuestrar instalaciones de org** (IDs enumerables, sobrescribe `user`) — `views.py`. Fix: verificar acceso vía `/user/installations` con el token del usuario; no sobrescribir owner de instalación de org ajena.
- **Create-repo confía en `installation_id` del cliente** y salta la verificación de membresía — `views.py` `GithubCreateRepoView`. Fix: resolver siempre vía `_resolve_org_installation_for_user`; check de membresía antes del create.
- **Access token en `localStorage`** (XSS → bearer reutilizable) — `src/services/api.ts`. Fix: token en memoria + refresh cookie HttpOnly.
- **Commit/Branches gatean en un link `ProjectRepo` auto-aseverado + fallback al token del usuario** — `views.py`. Fix: verificar admin/write real vía API de GitHub al linkear.

### Datos
- **Contador de cuota no atómico (lost updates / overshoot)** — `metering.py` `consume`/`check_and_consume`. Fix: `UPDATE ... SET col=col+1 WHERE col < :quota RETURNING col` (0 filas ⇒ agotado).

### Correctitud
- **`PaymentSuccess` valida `is_premium` (nivel usuario) para cobro per-proyecto** → toda compra exitosa queda "pending" — `src/app/pages/PaymentSuccess.tsx`. Fix: pasar `project` en `success_url` y sondear `getAiUsage(projectId)` hasta `plan==='pro'`.

---

## 🟡 Medios
- Cuota consumida ANTES de la llamada y también si Claude falla; el pending review encolado se borra al fallar → se pierde el retry — `webhook.py`, `chat.py`. Fix: consumir solo en éxito; no borrar pending al fallar.
- Sin handler `customer.subscription.updated` (plan/seat/past_due/reactivación no reconcilian) — `views.py StripeWebhookView`.
- Cancelación per-proyecto revoca premium global de usuario con múltiples proyectos Pro — `views.py`.
- Seat sync asume `items[0]` y traga todos los errores (deriva de facturación) — `views.py`.
- Alta/baja de miembros: COUNT-then-modify de asientos sin lock (cantidad facturada incorrecta en concurrencia) — `views.py`.
- `AuthContext.login` colapsa todo error en "email/contraseña incorrectos" — `src/app/context/AuthContext.tsx`.
- Profile "View premium plans" → `/plans` sin proyecto = callejón sin salida — `src/app/pages/Profile.tsx`.
- Token interno Django↔FastAPI reusa el secreto HMAC del webhook de GitHub; manda `''` si no está — `predictions.py`, `views.py`.
- `GithubChatProxyView` reenvía Authorization+body sin check de proyecto/cuota/membresía — `views.py`.
- OAuth state replayable / no ligado a sesión — `views.py`.
- Callbacks OAuth guardan token de fragment no verificado y derivan rol de claims JWT sin firmar — `src/app/pages/GoogleAuthCallback.tsx`, `GitHubAuthCallback.tsx`.
- Inyección de prompt: diff/código no confiable entra crudo al prompt y se aplica verbatim — `agent_service.py`.
- Refresh tokens stateless, no revocados en logout (replay hasta 7 días); aún se acepta el body-token legacy — `views.py`.

---

## ⚪ Bajos (resumen)
`isAdmin()` confía en JWT decodificado en cliente; `*_STATE_SECRET` caen a `JWT_SECRET_KEY`; tokens de instalación de org resueltos por `account_login` global; colaborador GitHub usa token admin del creador; `/predictions` sin cuota; `GithubAppDebugView` en producción; OAuth auto-provisiona cuenta saltando verificación; parsing de respuesta Anthropic asume `content[0]` texto; `current_period()` recalculado entre check/consume; `_get_or_create_usage` puede devolver None; pre-check de cuota Django TOCTOU (solo UI hint); `AiUsageCard` refetch sin guard de unmount; restos de `annual`; checkout concede premium sin verificar `payment_status`; constantes de cuota divergentes entre servicios; ProjectMember (FastAPI) PK compuesto sin `id`; CHECK `story_points>0` no reflejado en modelo; migración 0041 no idempotente; `Task.id_project` nullable mismatch; FKs faltantes en modelos SQLAlchemy; Integer vs BigInteger en todos los PK/FK de FastAPI.

---
*Rutas de backend relativas a `Yemoda_Backend/`; frontend en `YEMODA/YeMoDa_FrontEndActualizado/`.*
