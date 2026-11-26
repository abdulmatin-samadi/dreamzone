# Dreamzone — Foydalanish yo'riqnomasi

Sayt: **http://localhost:5173** (ishga tushirish: `./run.sh`)

## Umumiy g'oya

Markazga yangi o'quvchi keladi → resepshn uni ro'yxatga oladi va **saralash testi** (placement) topshirtiradi → natijaga qarab daraja (Elementary, Pre-Intermediate, Intermediate, Pre-IELTS) belgilanadi.
Keyinchalik o'quvchi yuqoriroq darajaga o'tmoqchi bo'lsa, o'qituvchi **darajani oshirish imtihoni** yaratadi → o'quvchi topshiradi → o'qituvchi tasdiqlasa, daraja oshadi.

Har bir imtihon har bir o'quvchi uchun **faqat bir marta** topshiriladi. Qayta topshirish yo'q (buni server o'zi cheklaydi).

## Kimdir qaysi login bilan kiradi

| Rol | Login / parol (demo) | Nima qila oladi |
|---|---|---|
| Admin | `admin` / `Admin12345!` | Hamma narsa |
| Resepshn | `reception` / `Demo12345!` | O'quvchi ro'yxatga olish, saralash testi |
| O'qituvchi | `teacher` / `Demo12345!` | Imtihon yaratish, biriktirish, tasdiqlash |
| O'quvchi | `student` / `Demo12345!` | Imtihon topshirish, natijani ko'rish |

Demo parollarni ish boshlashdan oldin almashtiring (Admin → Foydalanuvchilar → Parolni tiklash).
Admin va o'qituvchi yuqoridagi **UZ / EN** tugmasi bilan tilni almashtiradi (tanlov saqlanadi). Imtihon savollari tarjima qilinmaydi.

---

## 1. Admin: birinchi sozlash (bir marta)

1. **Foydalanuvchilar** → o'qituvchi va resepshn xodimlarini qo'shing (login, parol, rol).
2. **Savollar bazasi** → savollar kiriting:
   - Tur: bitta javob, bir nechta javob, To'g'ri/Noto'g'ri, bo'sh joy to'ldirish, moslashtirish, o'qib tushunish, tinglab tushunish.
   - Bo'lim: Grammatika / Lug'at / O'qish / Tinglash. Daraja, ball, izoh, rasm, audio ixtiyoriy.
   - O'qish savollari uchun "Matnlar" tabida umumiy matn yarating va bir nechta savolga ulang. Tinglash uchun audio yuklang.
3. **Darajalar** → har bir daraja qatorida **Saralash testi** ustuni bor: "Sozlash" bosing.
4. Saralash testi sahifasida:
   - **Variantlar** tabida variant (A, B…) qo'shing, "Savollar qo'shish" bilan savollarni tanlang (↑↓ bilan tartiblang).
   - **Sozlamalar** tabida davomiylik, **quyi chegara** (shundan past ball → oldingi daraja taklif qilinadi), **yuqori chegara** (shundan yuqori → keyingi daraja taklif qilinadi), ko'rsatma, aralashtirish.
   - Tepada **E'lon qilish** bosing. E'lon qilinmagan test hech kimga biriktirilmaydi.
5. **Guruhlar** → guruh yarating, o'qituvchi va daraja tanlang, "A'zolar" orqali o'quvchilarni qo'shing.

## 2. Resepshn: ro'yxatsiz tezkor test (asosiy yo'l)

1. **Saralash testlari** sahifasida **"Tezkor test"** kartasi: faqat darajani tanlang (ism ixtiyoriy) va **"Testni hozir boshlash"** bosing.
2. Hech kim ro'yxatga olinmaydi. Tizim ichkarida "Mehmon #N" yozuvini yaratadi (loginsiz), u **O'quvchilar** ro'yxatida va statistikada ko'rinmaydi.
3. O'quvchi testni yechadi, natija va daraja chiqadi (past/yuqori ballda boshqa daraja testi taklif qilinadi). Natija **Natijalar** bo'limida saqlanadi.
4. Agar o'quvchi o'qishga qoldi: saralash ro'yxatidagi mehmon qatorida **"O'quvchi qilib ro'yxatga olish"** → ism, familiya, telefon → login/parol chiqadi. Test natijasi va daraja saqlanadi, keyin guruhga qo'shasiz.

## 2a. O'quvchi o'zi ro'yxatdan o'tadi (ixtiyoriy yo'l)

1. Login sahifasida **"Ro'yxatdan o'ting"** bosiladi: ism, familiya, telefon, taxminiy daraja, parol. **Telefon raqami — login**.
2. Tizim avtomatik kiritadi va o'quvchiga tanlangan daraja saralash testini biriktiradi. O'quvchi **o'z sahifasidan** (Mening imtihonlarim) testni topshiradi.
3. Natijaga qarab daraja belgilanadi (past/yuqori ballda boshqa daraja testi taklif qilinadi — pastdagi qoidalar bilan bir xil).
4. Daraja aniqlangach, o'quvchi resepshn panelida **O'quvchilar → "Daraja aniq, guruhi yo'q"** filtrida chiqadi (bosh sahifada ham "Guruh kutmoqda" soni bor). Resepshn **Guruhga qo'shish** bosadi: o'quvchi darajasidagi guruhlar ★ bilan yuqorida turadi.

Test faqat bir marta topshiriladi. Ro'yxatga olishni resepshn ham qo'lda qila oladi (pastda).

## 2b. Resepshn: o'quvchini o'zi ro'yxatga olsa

1. **O'quvchilar** → **+ O'quvchini ro'yxatga olish**: ism, familiya, telefon, boshlang'ich (taxminiy) daraja, ixtiyoriy guruh.
2. Saqlagach **login va parol** chiqadi. Parol **faqat bir marta** ko'rsatiladi: yozib oling yoki "Chop etish" bosing. Yo'qolsa "Parolni tiklash".
3. **Saralash testlari** → o'quvchini ism yoki telefon bilan qidiring, daraja tanlang:
   - **Biriktirish va hozir boshlash** — imtihon shu kompyuterda darhol boshlanadi (o'quvchi to'liq ekranli test oynasini ko'radi).
   - **Faqat biriktirish** — keyinroq ro'yxatdan "Imtihonni boshlash" bosiladi.
4. O'quvchi testni yechadi. Natijadan keyin:
   - **Past ball** → "Joriy natijangiz B1 talablariga javob bermaydi. A2 testini topshirmoqchimisiz?" — *Ha, A2 ni topshiraman* / *Yo'q, yakunlash*.
   - **Yuqori ball** → "Ajoyib natija! B2 testini sinab ko'rasizmi?" — *Ha, B2* / *Yo'q, yakunlash*.
   - **O'rtacha ball** → daraja avtomatik tasdiqlanadi.
5. "Yakunlash va resepshnga qaytish" bosing. Natijalarni **Natijalar** bo'limidan ko'rasiz.

Qoidalar: "Ha" desa, boshqa daraja uchun yangi test biriktiriladi. Allaqachon topshirilgan daraja qayta taklif qilinmaydi. "Yo'q" desa: past natijada bir daraja pastga joylanadi, yuqori natijada sinalgan daraja saqlanadi.

## 3. O'qituvchi: darajani oshirish imtihoni

1. **Imtihonlar** → **+ Imtihon yaratish**: nom, joriy daraja (masalan B1), maqsad daraja (B2), davomiylik, o'tish bali.
2. **Variantlar** tabida variantlar yarating (A, B, C — har birida boshqa savollar bo'lishi mumkin) va savollar qo'shing. Savolni o'zingiz ham **Savollar bazasi**da yaratishingiz mumkin.
3. **E'lon qilish**.
4. **Biriktirish** tabida **guruhni** yoki alohida **o'quvchilarni** tanlang. Faqat joriy darajasi B1 bo'lgan o'quvchilar biriktiriladi.
   - Variant: "Tasodifiy" yoki aniq variant. O'quvchi variantni o'zgartira olmaydi.
   - Boshlanish/tugash vaqtini qo'ysangiz, imtihon faqat shu oraliqda ochiq bo'ladi.
5. O'quvchi topshirgach, natija **Daraja tasdiqlari** bo'limiga tushadi (faqat o'tganlar). Natijani ochib ko'ring (bo'limlar bo'yicha ball, javoblar) va **Tasdiqlash** yoki **Rad etish** bosing.
   - Tasdiqlansa o'quvchi darajasi B1 → B2 bo'ladi va tarixga yoziladi.
   - O'tmagan o'quvchi darajasi o'zgarmaydi, qayta urinish yo'q.
6. Tasdiqlangan qarorni o'qituvchi o'zgartira olmaydi. Faqat admin natija sahifasida "Administrator qarorini o'zgartirish" orqali izoh yozib o'zgartiradi (daraja avtomatik qaytariladi/qo'llanadi).

Boshqa bo'limlar: **Mening o'quvchilarim / guruhlarim** (faqat o'zingizniki), **Jadval** (biriktirilgan imtihonlar), **Imtihonlar tarixi** (filtr + Excel/PDF eksport), imtihon ichida **Statistika** (o'tish ulushi, qaysi savol qiyin).
Imtihonni birorta o'quvchi topshirgach, uning savollari va darajasi **qulflanadi**, o'chirib bo'lmaydi.

## 4. O'quvchi: imtihon topshirish

1. Login qiling → **Mening imtihonlarim** → imtihonda **Ko'rsatma va boshlash**.
2. Ko'rsatmani o'qing, **Imtihonni boshlash** bosing. Tepada **qolgan vaqt** (5 daqiqadan kam qolsa qizaradi).
3. Savollar orasida o'ng paneldagi raqamlar bilan erkin yuring. Javoblar **avtomatik saqlanadi**.
4. Sahifa yangilansa yoki internet uzilsa — qaytib kirsangiz **xuddi shu imtihon** va qolgan vaqt bilan davom etasiz.
5. **Yakunlash** → tasdiqlang. Vaqt tugasa, imtihon o'zi topshiriladi (yechilgan javoblar hisoblanadi).
6. Natija: umumiy foiz, to'g'ri/xato soni, bo'limlar bo'yicha ball (masalan Grammatika 20/25). Darajani oshirish imtihonida natija o'qituvchi tasdig'ini kutadi.
   To'g'ri javoblar faqat o'qituvchi "topshirgandan keyin ko'rsatish"ni yoqqan bo'lsa ko'rinadi.

---

## Savollar-javoblar

**O'quvchi imtihonni tasodifan yopib qo'ydi.** Qayta kirsa, davom ettiradi (vaqt to'xtamaydi). Vaqt tugagan bo'lsa, avtomatik topshirilgan bo'ladi.

**Imtihonni qayta topshirtirish kerak.** Tizim buni ruxsat etmaydi. Yangi imtihon yarating va o'quvchiga biriktiring.

**Saralash testida natija noto'g'ri chiqdi, darajani o'zgartirish kerak.** Admin → O'quvchilar → o'quvchi sahifasi → **Darajani o'zgartirish**. Hammasi daraja tarixida saqlanadi.

**O'quvchi parolini unutdi.** Resepshn yoki admin: O'quvchilar → **Parolni tiklash**.

**Natijalarni Excel/PDF qilish.** Natijalar sahifasida filtr qo'ying (daraja, o'qituvchi, sana…) → **Excel** yoki **PDF** tugmasi. Bitta natijaning PDF'i — natija sahifasida.

**Yangi til qo'shish.** `frontend/src/i18n/locales/` ichida yangi fayl yarating (uz.ts bilan bir xil kalitlar) va `frontend/src/i18n/index.ts` ga qo'shing.
