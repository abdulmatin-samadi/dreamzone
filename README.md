# Dreamzone — Placement Test & Level Upgrade System

Django 5 + DRF + PostgreSQL + JWT (backend) · React + TypeScript + Tailwind (frontend) · Celery/Redis (auto-submit sweeper).

## Tez ishga tushirish

```bash
# 1) Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # DB_ENGINE=sqlite qilsangiz PostgreSQL shart emas
createdb dreamzone              # PostgreSQL uchun
python manage.py migrate
python manage.py seed_demo      # 4 daraja (Elementary, Pre-Intermediate, Intermediate, Pre-IELTS), saralash testlari, demo akkauntlar
python manage.py runserver 8000

# 2) Frontend (boshqa terminalda)
cd frontend
npm install
npm run dev                     # http://localhost:5173  (API ga proxy: VITE_PROXY_TARGET, default :8000)
```

Demo loginlar (`seed_demo`): `admin / Admin12345!` · `reception`, `teacher`, `student` / `Demo12345!`.
**Ishlab chiqarishda parollarni almashtiring.** Saralash testlariga `seed_demo` faqat 2 tadan namunaviy savol qo'shadi — haqiqiy savollarni Admin panelidan kiriting.

Redis/Celery ixtiyoriy: `CELERY_BROKER_URL` bo'sh bo'lsa vazifalar eager rejimda ishlaydi, vaqti tugagan urinishlar esa baribir har so'rovda (lazy) avtomatik topshiriladi. To'liq stek: `docker compose up --build`
(worker `celery -A config worker`, beat har 30 soniyada muddati o'tgan urinishlarni topshiradi).

## Testlar

```bash
cd backend && python manage.py test apps                      # PostgreSQL
cd backend && DB_ENGINE=sqlite python manage.py test apps     # SQLite
cd frontend && npm run typecheck && npm run check:i18n && npm run build
```

## Arxitektura

| App | Mazmun |
|---|---|
| `accounts` | User (role, language), TeacherProfile, JWT login/refresh/logout, parol |
| `academics` | Level (Elementary … Pre-IELTS), Group |
| `students` | StudentProfile, StudentGroup, LevelChangeHistory, ro'yxatga olish |
| `questions` | Question, AnswerOption, Passage, **grading.py** (sof baholash funksiyalari) |
| `examinations` | Examination, Variant, Assignment, **Attempt**, StudentAnswer, **services.py** (start/autosave/submit) |
| `results` | ExamResult, **services.py** (baholash, tavsiya, tasdiq, override), eksport (PDF/Excel) |
| `analytics` | Dashboard, statistika |

Muhim qoidalar (hammasi **backendda** majburlanadi):
- **Bir martalik imtihon**: `ExamAssignment (exam, student)` unique, `ExamAttempt.assignment` OneToOne. `start` idempotent — refresh/qayta ulanishda xuddi shu urinish va qolgan vaqt qaytadi; yakunlangan urinishga `409 attempt_already_finished`.
- **Vaqt**: `deadline_at` serverda; tugaganda `submit_attempt(auto=True)` (lazy + Celery). Saqlangan javoblar baholanadi.
- **Tranzaksiya + qulf**: `select_for_update` bilan start/submit/tasdiq/daraja o'zgarishi.
- **Javoblar sirli**: o'quvchi payload'ida `is_correct` yo'q; to'g'ri javoblar faqat xodimlarga (yoki `show_correct_answers` yoqilgan bo'lsa topshirgandan keyin).
- **Saralash**: foiz < `passing_score` → oldingi daraja taklifi; ≥ `high_threshold` → keyingi daraja; aks holda tasdiq. Chegaralarni admin imtihon sozlamasida o'zgartiradi. Taklif qabul qilinsa boshqa daraja uchun yangi assignment/urinish yaratiladi; avval biriktirilgan daraja qayta taklif qilinmaydi.
  Taklifni rad etish: past natijada bir daraja pastga joylanadi, yuqori natijada sinalgan daraja saqlanadi.
- **Darajani oshirish**: o'tgan natija `PENDING` → o'qituvchi tasdiqlaydi → daraja o'zgaradi (`LevelChangeHistory`). Qaror qulflangan; faqat admin `override` qila oladi (daraja avtomatik qaytariladi/qo'llanadi). O'tmagan o'quvchi darajasi o'zgarmaydi, qayta urinish yo'q.
- **Resepshn kiosk**: resepshn "Boshlash" bosganda o'quvchi uchun qisqa muddatli, faqat imtihon endpointlariga ishlaydigan `kiosk` JWT beriladi.
- **Ballash**: savol bo'yicha "hammasi yoki hech narsa" (MSQ va Matching ham). Fill-in: katta-kichik harf/bo'shliq inobatga olinmaydi.
- **Tillar**: Admin/Teacher uchun UZ/EN (header'da almashtirgich, `User.language` ga saqlanadi); yangi til — `frontend/src/i18n/locales/<kod>.ts` + `i18n/index.ts` ga qo'shish. Savol matnlari tarjima qilinmaydi. Resepshn va o'quvchi — o'zbekcha.

## API (prefiks `/api/v1/`)

`auth/{login,refresh,logout,me,change-password}` · `users` · `levels` · `groups[/id/members]` · `students[/id/{report,reset-password,set-level}]` · `level-history` · `questions` · `passages` · `examinations[/id/{publish,unpublish,assign}]` · `variants[/id/questions]` · `assignments` · `placements[/id/start]` · `my/assignments` · `assignments/id/start` · `attempts/id[/answers|/submit]` · `results[/id/{approve,reject,override,offer,export}]` · `results/export/?file=xlsx|pdf` · `analytics/{dashboard,results-summary,examinations/id}`

## Eslatma
Yozish (writing) va speaking hozircha yo'q. Eksport PDF'i standart shriftda — o'zbekcha maxsus harflar (oʻ, gʻ) PDF'da to'liq ko'rinmasligi mumkin (Excel'da muammo yo'q).
