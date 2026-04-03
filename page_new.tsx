'use client';

import { useEffect } from 'react';
import Image from 'next/image';

export default function Home() {
  useEffect(() => {
    // ===== Полоса прогресса скролла =====
    const progressBar = document.getElementById('scroll-progress');
    const handleScroll = () => {
        if (!progressBar) return;
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
        progressBar.style.width = progress + '%';
    };
    window.addEventListener('scroll', handleScroll);

    // ===== Intersection Observer для анимаций =====
    const revealClasses = ['.reveal', '.reveal-left', '.reveal-right', '.reveal-scale'];
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll(revealClasses.join(', ')).forEach(el => observer.observe(el));

    // ===== 3D Tilt эффект для карточек товаров =====
    document.querySelectorAll('[data-tilt]').forEach(card => {
        const inner = card.querySelector('.product-card-inner');
        const MAX_TILT = 12;

        const handleMouseMove = (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const cx = rect.width / 2;
            const cy = rect.height / 2;

            const rotateX = ((y - cy) / cy) * -MAX_TILT;
            const rotateY = ((x - cx) / cx) * MAX_TILT;

            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.03,1.03,1.03)`;

            if (inner) {
                inner.style.setProperty('--mx', x + 'px');
                inner.style.setProperty('--my', y + 'px');
            }
        };

        const handleMouseLeave = () => {
            card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)';
            card.style.transition = 'transform 0.5s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.5s ease';
            setTimeout(() => { card.style.transition = ''; }, 500);
        };

        const handleMouseEnter = () => {
            card.style.transition = 'transform 0.1s ease, box-shadow 0.3s ease';
        };

        card.addEventListener('mousemove', handleMouseMove);
        card.addEventListener('mouseleave', handleMouseLeave);
        card.addEventListener('mouseenter', handleMouseEnter);
    });

    return () => {
        window.removeEventListener('scroll', handleScroll);
        observer.disconnect();
    };
  }, []);

  return (
    <>


    {/*  Полоса прогресса скролла  */}
    <div id="scroll-progress" style={{ width: '0%' }}></div>

    {/*  Декоративные блобы  */}
    <div className="blob bg-blue-600 w-[700px] h-[700px] top-[-200px] left-[-200px]"></div>
    <div className="blob bg-purple-700 w-[600px] h-[600px] top-[40%] right-[-150px]"></div>
    <div className="blob bg-pink-600 w-[500px] h-[500px] bottom-[-100px] left-[30%]"></div>

    {/*  ===================== ШАПКА =====================  */}
    <nav className="glass-strong">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between max-w-7xl">
            <a href="#" className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-xl btn-primary flex items-center justify-center pulse">
                    <span className="text-white font-black text-sm">N</span>
                </div>
                <span className="text-xl font-black tracking-tight">Next <span className="gradient-text">Gadget</span></span>
            </a>
            <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-300">
                <a href="#features" className="hover:text-white transition-colors">Возможности</a>
                <a href="#choose" className="hover:text-white transition-colors">Гаджеты</a>
                <a href="#why" className="hover:text-white transition-colors">О нас</a>
            </div>
            <div className="flex items-center gap-3">
                <a href="#choose" className="btn-primary px-4 py-2 rounded-xl text-sm font-semibold text-white">
                    Выбрать гаджет
                </a>
            </div>
        </div>
    </nav>

    {/*  ===================== HERO =====================  */}
    <section className="min-h-screen flex items-center">
        <div className="container mx-auto px-6 py-24 max-w-7xl">
            <div className="flex flex-col lg:flex-row items-center gap-16">

                {/*  Текст  */}
                <div className="w-full lg:w-1/2 space-y-8 reveal-left">
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass text-sm font-medium text-blue-300">
                        <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
                        Платформа умных технологий
                    </div>
                    <h1 className="text-6xl md:text-7xl font-black leading-[1.05] tracking-tight">
                        Next<br>
                        <span className="gradient-text">Gadget!</span>
                    </h1>
                    <p className="text-xl text-gray-400 leading-relaxed max-w-lg">
                        Экосистема умных устройств нового поколения. Умное управление и бизнес-экосистема, работающие совместно с гаджетами для развлечений.
                    </p>
                    <div className="flex flex-wrap gap-4 pt-2">
                        <a href="#choose" className="btn-primary px-7 py-4 rounded-2xl font-bold text-base text-white flex items-center gap-2">
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"/></svg>
                            Выбрать гаджет
                        </a>
                    </div>
                    <div className="flex items-center gap-8 pt-4">
                        <div>
                            <div className="text-3xl font-black gradient-text">500+</div>
                            <div className="text-gray-500 text-sm">устройств</div>
                        </div>
                        <div className="w-px h-10 bg-white/10"></div>
                        <div>
                            <div className="text-3xl font-black gradient-text">50K+</div>
                            <div className="text-gray-500 text-sm">пользователей</div>
                        </div>
                        <div className="w-px h-10 bg-white/10"></div>
                        <div>
                            <div className="text-3xl font-black gradient-text">24/7</div>
                            <div className="text-gray-500 text-sm">поддержка</div>
                        </div>
                    </div>
                </div>

                {/*  Визуал  */}
                <div className="w-full lg:w-1/2 flex justify-center reveal-right">
                    <div className="relative float">
                        <div className="glass-strong rounded-3xl p-8 w-72 h-80 flex flex-col justify-between shadow-2xl">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl btn-primary flex items-center justify-center text-white font-black">N</div>
                                <div>
                                    <div className="text-sm font-bold">Next Hub</div>
                                    <div className="text-xs text-gray-400">Все устройства онлайн</div>
                                </div>
                                <div className="ml-auto w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
                            </div>
                            <div className="space-y-3">
                                <div className="glass rounded-xl p-3 flex items-center gap-3">
                                    <span className="text-xl">📱</span>
                                    <div className="flex-1">
                                        <div className="text-xs font-semibold">Смартфон</div>
                                        <div className="text-xs text-gray-400">Подключён</div>
                                    </div>
                                    <div className="w-2 h-2 rounded-full bg-green-400"></div>
                                </div>
                                <div className="glass rounded-xl p-3 flex items-center gap-3">
                                    <span className="text-xl">💻</span>
                                    <div className="flex-1">
                                        <div className="text-xs font-semibold">Ноутбук</div>
                                        <div className="text-xs text-gray-400">Подключён</div>
                                    </div>
                                    <div className="w-2 h-2 rounded-full bg-green-400"></div>
                                </div>
                                <div className="glass rounded-xl p-3 flex items-center gap-3">
                                    <span className="text-xl">⌚</span>
                                    <div className="flex-1">
                                        <div className="text-xs font-semibold">Смарт-часы</div>
                                        <div className="text-xs text-gray-400">Синхронизация</div>
                                    </div>
                                    <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse"></div>
                                </div>
                            </div>
                            <button className="btn-primary w-full py-3 rounded-xl text-sm font-bold text-white">
                                Управлять →
                            </button>
                        </div>
                        {/*  Декоративные карточки позади  */}
                        <div className="absolute -top-4 -right-4 glass rounded-2xl p-4 w-36 text-center shadow-xl">
                            <div className="text-2xl mb-1">🚀</div>
                            <div className="text-xs font-semibold">Мгновенная синхронизация</div>
                        </div>
                        <div className="absolute -bottom-4 -left-4 glass rounded-2xl p-4 w-36 text-center shadow-xl">
                            <div className="text-2xl mb-1">🔒</div>
                            <div className="text-xs font-semibold">Полная безопасность</div>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </section>

    {/*  ===================== ВОЗМОЖНОСТИ =====================  */}
    <section id="features" className="py-28">
        <div className="container mx-auto px-6 max-w-7xl">
            <div className="text-center mb-20 reveal">
                <div className="inline-block px-4 py-2 rounded-full glass text-sm font-medium text-purple-300 mb-5">
                    ✦ Функционал
                </div>
                <h2 className="text-5xl md:text-6xl font-black mb-5">
                    Максимум контента<br>
                    <span className="gradient-text">и возможностей</span>
                </h2>
                <p className="text-gray-400 text-xl max-w-2xl mx-auto">
                    Всё, что нужно для идеального отдыха и развлечений — в одной приставке
                </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-1">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-blue-500 text-white shadow-lg shadow-blue-500/30">📺</div>
                    <h3 className="text-lg font-bold">Более 1600 каналов</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Федеральные и региональные каналы в HD качестве. Новости, спорт, развлечения и детские программы.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-2">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-purple-500 text-white shadow-lg shadow-purple-500/30">🎬</div>
                    <h3 className="text-lg font-bold">50,000+ фильмов и сериалов</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Огромная библиотека контента. От классики до новинок кино. Постоянные обновления каталога.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-3">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-green-500 text-white shadow-lg shadow-green-500/30">📻</div>
                    <h3 className="text-lg font-bold">Радиостанции и музыка</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Популярные радиостанции и музыкальные клипы. Создавайте свои плейлисты и наслаждайтесь музыкой.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-4">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-pink-500 text-white shadow-lg shadow-pink-500/30">🎤</div>
                    <h3 className="text-lg font-bold">Караоке-сервис</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Тысячи песен для караоке с профессиональными минусовками. Пойте с друзьями и семьей.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-5">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-orange-500 text-white shadow-lg shadow-orange-500/30">🗣️</div>
                    <h3 className="text-lg font-bold">Голосовое управление</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Управляйте приставкой голосом. Ищите контент, переключайте каналы и управляйте воспроизведением.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-6">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-teal-500 text-white shadow-lg shadow-teal-500/30">📶</div>
                    <h3 className="text-lg font-bold">Стабильная работа</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Оптимизированный Android TV лаунчер. Быстрая загрузка и стабильная работа без зависаний.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-1">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/30">📥</div>
                    <h3 className="text-lg font-bold">Офлайн режим</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Скачивайте любимые фильмы и сериалы для просмотра без интернета. Берите развлечения с собой.</p>
                </div>
                <div className="glass card-hover card-glow rounded-2xl p-7 flex flex-col gap-4 reveal delay-2">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl bg-red-500 text-white shadow-lg shadow-red-500/30">🛡️</div>
                    <h3 className="text-lg font-bold">Безопасность</h3>
                    <p className="text-gray-400 text-sm leading-relaxed">Защищенный контент и родительский контроль. Создавайте профили для всех членов семьи.</p>
                </div>
            </div>
        </div>
    </section>

    {/*  ===================== ВЫБЕРИТЕ NEXT =====================  */}
    <section id="choose" className="py-28">
        <div className="container mx-auto px-6 max-w-7xl">
            <div className="text-center mb-20 reveal">
                <div className="inline-block px-4 py-2 rounded-full glass text-sm font-medium text-blue-300 mb-5">
                    ✦ Умные гаджеты
                </div>
                <h2 className="text-5xl md:text-6xl font-black mb-5">
                    Выберите Ваш<br>
                    <span className="gradient-text">Next</span>
                </h2>
                <p className="text-gray-400 text-xl max-w-2xl mx-auto">
                    Три модели ТВ-приставок — для любого бюджета и задачи
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-start">

                {/*  ══ NEXT One ══  */}
                <div className="product-card one reveal-scale delay-1" data-tilt>
                    {/*  Градиентная рамка  */}
                    <div className="absolute inset-0 rounded-[28px] border-one" style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(59,130,246,0.6), rgba(99,102,241,0.2), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}></div>

                    <div className="product-card-inner">
                        {/*  Бейдж хит  */}
                        <div className="absolute top-5 left-5 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black text-white"
                             style={{ background: 'linear-gradient(135deg,#3b82f6,#6366f1)', boxShadow: '0 4px 15px rgba(59,130,246,0.4)' }}>
                            🔥 Хит продаж
                        </div>

                        {/*  Витрина  */}
                        <div className="product-stage stage-one mt-4">
                            <div className="product-stage-glow glow-one"></div>
                            <img src="images/next_one.png" alt="Next One" className="product-img"
                                  />
                        </div>

                        {/*  Название + описание  */}
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <h3 className="text-2xl font-black">Next One</h3>
                                <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-blue-300" style={{ background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.2)' }}>Full HD</span>
                            </div>
                            <p className="text-gray-400 text-sm leading-relaxed">Компактное решение для цифрового ТВ и стриминга. Более 1600 каналов и все популярные приложения.</p>
                        </div>

                        {/*  Характеристики  */}
                        <div className="grid grid-cols-2 gap-2">
                            <div className="spec-tag">💾 <span>2 ГБ ОЗУ</span></div>
                            <div className="spec-tag">💿 <span>16 ГБ</span></div>
                            <div className="spec-tag">🖥️ <span>Full HD</span></div>
                            <div className="spec-tag">📶 <span>Wi-Fi 5</span></div>
                        </div>

                        {/*  Цена  */}
                        <div className="flex items-end gap-3 pt-1">
                            <span className="text-4xl font-black" style={{ background: 'linear-gradient(135deg,#60a5fa,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>2 990 ₽</span>
                            <span className="text-gray-500 line-through text-base mb-1">3 990 ₽</span>
                            <span className="text-xs font-bold text-emerald-400 mb-1 ml-auto">−25%</span>
                        </div>

                        {/*  Маркетплейс  */}
                        <div className="space-y-2 mt-auto">
                            <p className="text-xs text-gray-600 font-semibold uppercase tracking-widest">Купить:</p>
                            <a href="https://www.wildberries.ru/catalog/274191851/detail.aspx" target="_blank" className="mp-btn group">
                                <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black text-white shrink-0 transition-transform group-hover:scale-110"
                                     style={{ background: 'linear-gradient(135deg,#7c3aed,#a855f7)' }}>WB</div>
                                <div className="flex-1">
                                    <div className="text-sm font-bold text-white">Wildberries</div>
                                    <div className="text-xs text-emerald-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span> В наличии</div>
                                </div>
                                <svg className="w-4 h-4 text-gray-500 group-hover:text-white group-hover:translate-x-0.5 transition-all shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                            </a>
                        </div>
                    </div>
                </div>

                {/*  ══ NEXT Pro ══  */}
                <div className="product-card pro reveal-scale delay-2" data-tilt style={{ marginTop: '-12px' }}>
                    {/*  Рамка  */}
                    <div className="absolute inset-0 rounded-[28px]" style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(139,92,246,0.7), rgba(168,85,247,0.3), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}></div>

                    <div className="product-card-inner">
                        {/*  Бейдж популярное  */}
                        <div className="absolute top-5 left-5 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black text-white"
                             style={{ background: 'linear-gradient(135deg,#7c3aed,#a855f7)', boxShadow: '0 4px 15px rgba(139,92,246,0.5)' }}>
                            ⭐ Популярное
                        </div>

                        {/*  Витрина  */}
                        <div className="product-stage stage-pro mt-4">
                            <div className="product-stage-glow glow-pro"></div>
                            <img src="images/next_pro.png" alt="Next Pro" className="product-img"
                                  />
                        </div>

                        {/*  Название  */}
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <h3 className="text-2xl font-black">Next Pro</h3>
                                <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-purple-300" style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.25)' }}>4K HDR</span>
                            </div>
                            <p className="text-gray-400 text-sm leading-relaxed">Мощная Android TV приставка с поддержкой 4K HDR. Облачный гейминг, свой магазин приложений.</p>
                        </div>

                        {/*  Характеристики  */}
                        <div className="grid grid-cols-2 gap-2">
                            <div className="spec-tag">💾 <span>2 ГБ ОЗУ</span></div>
                            <div className="spec-tag">💿 <span>16 ГБ</span></div>
                            <div className="spec-tag">🖥️ <span>4K HDR</span></div>
                            <div className="spec-tag">📶 <span>Wi-Fi 5</span></div>
                        </div>

                        {/*  Цена  */}
                        <div className="flex items-end gap-3 pt-1">
                            <span className="text-4xl font-black" style={{ background: 'linear-gradient(135deg,#a78bfa,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>4 990 ₽</span>
                            <span className="text-gray-500 line-through text-base mb-1">6 990 ₽</span>
                            <span className="text-xs font-bold text-emerald-400 mb-1 ml-auto">−28%</span>
                        </div>

                        {/*  Маркетплейс  */}
                        <div className="space-y-2 mt-auto">
                            <p className="text-xs text-gray-600 font-semibold uppercase tracking-widest">Купить:</p>
                            <a href="https://www.ozon.ru/product/mediapleer-android-2-gb-16-gb-bluetooth-ik-port-irda-2560760943/?oos_search=false" target="_blank" className="mp-btn group">
                                <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black text-white shrink-0 transition-transform group-hover:scale-110"
                                     style={{ background: 'linear-gradient(135deg,#0065ff,#005bde)' }}>OZ</div>
                                <div className="flex-1">
                                    <div className="text-sm font-bold text-white">Ozon</div>
                                    <div className="text-xs text-emerald-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span> В наличии</div>
                                </div>
                                <svg className="w-4 h-4 text-gray-500 group-hover:text-white group-hover:translate-x-0.5 transition-all shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                            </a>
                        </div>
                    </div>
                </div>

                {/*  ══ NEXT Air ══  */}
                <div className="product-card air reveal-scale delay-3" data-tilt>
                    {/*  Рамка  */}
                    <div className="absolute inset-0 rounded-[28px]" style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(16,185,129,0.6), rgba(5,150,105,0.2), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}></div>

                    <div className="product-card-inner">
                        {/*  Бейдж новинка  */}
                        <div className="absolute top-5 left-5 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-black text-white"
                             style={{ background: 'linear-gradient(135deg,#059669,#10b981)', boxShadow: '0 4px 15px rgba(16,185,129,0.4)' }}>
                            ✦ Новинка 2026
                        </div>

                        {/*  Витрина  */}
                        <div className="product-stage stage-air mt-4">
                            <div className="product-stage-glow glow-air"></div>
                            <img src="images/next_air.png" alt="Next Air" className="product-img"
                                  />
                        </div>

                        {/*  Название  */}
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <h3 className="text-2xl font-black">Next Air</h3>
                                <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-emerald-300" style={{ background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.25)' }}>4K HDR</span>
                            </div>
                            <p className="text-gray-400 text-sm leading-relaxed">Ультра-компактная приставка нового поколения. Компактнее и легче Pro, при этом не уступает в мощности.</p>
                        </div>

                        {/*  Характеристики  */}
                        <div className="grid grid-cols-2 gap-2">
                            <div className="spec-tag">💾 <span>2 ГБ ОЗУ</span></div>
                            <div className="spec-tag">💿 <span>16 ГБ</span></div>
                            <div className="spec-tag">🖥️ <span>4K HDR</span></div>
                            <div className="spec-tag">📶 <span>Wi-Fi 5</span></div>
                        </div>

                        {/*  Цена  */}
                        <div className="flex items-end gap-3 pt-1">
                            <span className="text-4xl font-black" style={{ background: 'linear-gradient(135deg,#34d399,#10b981)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>3 990 ₽</span>
                        </div>

                        {/*  Маркетплейс  */}
                        <div className="space-y-2 mt-auto">
                            <p className="text-xs text-gray-600 font-semibold uppercase tracking-widest">Купить:</p>
                            <a href="https://www.ozon.ru/product/mediapleer-android-2-gb-16-gb-ik-port-irda-wi-fi-chernyy-2184956813/" target="_blank" className="mp-btn group">
                                <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black text-white shrink-0 transition-transform group-hover:scale-110"
                                     style={{ background: 'linear-gradient(135deg,#0065ff,#005bde)' }}>OZ</div>
                                <div className="flex-1">
                                    <div className="text-sm font-bold text-white">Ozon</div>
                                    <div className="text-xs text-emerald-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span> В наличии</div>
                                </div>
                                <svg className="w-4 h-4 text-gray-500 group-hover:text-white group-hover:translate-x-0.5 transition-all shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                            </a>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </section>

    {/*  ===================== ПОЧЕМУ NEXT =====================  */}
    <section id="why" className="py-28">
        <div className="container mx-auto px-6 max-w-7xl">
            <div className="flex flex-col lg:flex-row items-center gap-16">
                {/*  Текст  */}
                <div className="w-full lg:w-1/2 space-y-8 reveal-left">
                    <div className="inline-block px-4 py-2 rounded-full glass text-sm font-medium text-pink-300">
                        ✦ О платформе
                    </div>
                    <h2 className="text-5xl md:text-6xl font-black leading-tight">
                        Почему выбирают<br>
                        <span className="gradient-text">Next?</span>
                    </h2>
                    <p className="text-gray-400 text-lg leading-relaxed">
                        Мы создаём не просто устройства — мы строим единую экосистему, в которой каждый гаджет работает умнее вместе с другими.
                    </p>
                    <div className="space-y-5">
                        <div className="flex items-start gap-4">
                            <div className="w-12 h-12 rounded-xl bg-blue-500/15 border border-blue-500/20 flex items-center justify-center text-xl shrink-0">🌐</div>
                            <div>
                                <h4 className="font-bold text-lg mb-1">Единая экосистема</h4>
                                <p className="text-gray-400 text-sm">Все устройства работают вместе — телефон, ноутбук, часы, умный дом.</p>
                            </div>
                        </div>
                        <div className="flex items-start gap-4">
                            <div className="w-12 h-12 rounded-xl bg-purple-500/15 border border-purple-500/20 flex items-center justify-center text-xl shrink-0">⚡</div>
                            <div>
                                <h4 className="font-bold text-lg mb-1">Скорость и надёжность</h4>
                                <p className="text-gray-400 text-sm">99.9% uptime и молниеносная синхронизация данных по всем устройствам.</p>
                            </div>
                        </div>
                        <div className="flex items-start gap-4">
                            <div className="w-12 h-12 rounded-xl bg-pink-500/15 border border-pink-500/20 flex items-center justify-center text-xl shrink-0">🛠️</div>
                            <div>
                                <h4 className="font-bold text-lg mb-1">Поддержка 24/7</h4>
                                <p className="text-gray-400 text-sm">Команда экспертов всегда на связи. Среднее время ответа — меньше 5 минут.</p>
                            </div>
                        </div>
                    </div>
                </div>
                {/*  Статистика  */}
                <div className="w-full lg:w-1/2 grid grid-cols-2 gap-5 reveal-right">
                    <div className="glass-strong rounded-3xl p-8 text-center reveal delay-1">
                        <div className="text-5xl font-black gradient-text mb-2">500+</div>
                        <div className="text-gray-400 text-sm font-medium">Совместимых устройств</div>
                    </div>
                    <div className="glass-strong rounded-3xl p-8 text-center reveal delay-2">
                        <div className="text-5xl font-black gradient-text mb-2">50K+</div>
                        <div className="text-gray-400 text-sm font-medium">Активных пользователей</div>
                    </div>
                    <div className="glass-strong rounded-3xl p-8 text-center reveal delay-3">
                        <div className="text-5xl font-black gradient-text mb-2">99.9%</div>
                        <div className="text-gray-400 text-sm font-medium">Время работы</div>
                    </div>
                    <div className="glass-strong rounded-3xl p-8 text-center reveal delay-4">
                        <div className="text-5xl font-black gradient-text mb-2">4.9★</div>
                        <div className="text-gray-400 text-sm font-medium">Рейтинг в магазинах</div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/*  ===================== NEXT OS CHARA =====================  */}
    <section id="chara" className="py-28 relative">
        <div className="container mx-auto px-6 max-w-7xl">
            <div className="text-center mb-20 reveal">
                <div className="inline-block px-4 py-2 rounded-full glass text-sm font-medium text-blue-300 mb-5">
                    ✦ Next OS Chara
                </div>
                <h2 className="text-5xl md:text-6xl font-black mb-5">
                    Операционная система<br>
                    <span className="gradient-text">для умных ТВ-приставок</span>
                </h2>
                <p className="text-gray-400 text-xl max-w-2xl mx-auto">
                    Быстро. Чисто. Умно. Всё, что нужно для идеального ТВ-опыта — в одной системе.
                </p>
            </div>

            {/*  Особенности и преимущества  */}
            <div className="mb-24">
                <h3 className="text-4xl font-black mb-12 text-center reveal">Особенности и преимущества</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-1">
                        <div className="text-3xl shrink-0">⚡</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Мгновенная загрузка</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Приставка готова к работе уже через секунды.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-2">
                        <div className="text-3xl shrink-0">🧼</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Чистый интерфейс</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Без лишних элементов, перегрузки и рекламы.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-3">
                        <div className="text-3xl shrink-0">📺</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">1600+ ТВ-каналов</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Огромная библиотека телеканалов без регистрации и рекламы.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-4">
                        <div className="text-3xl shrink-0">📦</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Предустановленные приложения</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">YouTube, IVI, Wink, Kinopoisk, HD VideoBox и другие.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-5">
                        <div className="text-3xl shrink-0">🛒</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Собственный магазин</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Только проверенные и совместимые программы.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-6">
                        <div className="text-3xl shrink-0">🎤</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Голосовой помощник Bro</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Слушает, понимает и помогает управлять приставкой голосом.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-1">
                        <div className="text-3xl shrink-0">🤖</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Индивидуальные рекомендации</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Умная система подбирает контент под интересы пользователя.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-2">
                        <div className="text-3xl shrink-0">🧒</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Детский режим</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Безопасный и понятный интерфейс для детей.</p>
                        </div>
                    </div>
                    <div className="glass rounded-2xl p-6 hover:bg-white/5 transition-colors flex gap-4 reveal delay-3">
                        <div className="text-3xl shrink-0">🔄</div>
                        <div>
                            <h4 className="font-bold text-lg mb-1">Стабильные обновления</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">Автоматические апдейты каждую неделю.</p>
                        </div>
                    </div>
                </div>
            </div>

            {/*  Галерея  */}
            <div className="mb-24">
                <h3 className="text-3xl font-black mb-10 text-center reveal">Галерея интерфейса и приложений</h3>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    <div className="space-y-4 reveal-left delay-1">
                        <div className="glass-strong rounded-2xl aspect-video flex items-center justify-center overflow-hidden relative group">
                            <img src="images/chara_main.png" alt="Main Screen" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                        </div>
                        <h4 className="text-xl font-bold text-center">Main Screen</h4>
                        <p className="text-gray-400 text-sm text-center">Главный экран. Быстрый доступ ко всем любимым приложениям, каналам и рекомендациям.</p>
                    </div>
                    <div className="space-y-4 reveal delay-3">
                        <div className="glass-strong rounded-2xl aspect-video flex items-center justify-center overflow-hidden relative group">
                            <img src="images/chara_selection.png" alt="Selection" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                        </div>
                        <h4 className="text-xl font-bold text-center">Selection</h4>
                        <p className="text-gray-400 text-sm text-center">Специальная подборка контента, которая анализирует ваши предпочтения.</p>
                    </div>
                    <div className="space-y-4 reveal-right delay-5">
                        <div className="glass-strong rounded-2xl aspect-video flex items-center justify-center overflow-hidden relative group">
                            <img src="images/chara_library.png" alt="Library" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                        </div>
                        <h4 className="text-xl font-bold text-center">Library</h4>
                        <p className="text-gray-400 text-sm text-center">Встроенный магазин приложений. Только проверенные и совместимые программы.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/*  ===================== КОНТАКТЫ (CTA) =====================  */}
    <section id="contacts" className="py-28">
        <div className="container mx-auto px-6 max-w-4xl">
            <div className="glass-strong rounded-3xl p-12 md:p-16 text-center relative overflow-hidden reveal-scale">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-600/10 to-purple-600/10 rounded-3xl"></div>
                <div className="relative z-10">
                    <div className="inline-block px-4 py-2 rounded-full glass text-sm font-medium text-purple-300 mb-6">
                        ✦ Контакты
                    </div>
                    <h2 className="text-5xl md:text-6xl font-black mb-6">
                        Свяжитесь<br><span className="gradient-text">с нами</span>
                    </h2>
                    <p className="text-gray-400 text-xl mb-10 max-w-2xl mx-auto">
                        Мы всегда на связи и готовы ответить на ваши вопросы.
                    </p>
                    
                    {/*  Кнопка Telegram  */}
                    <div className="flex justify-center mb-8">
                        <a href="https://t.me/NEXTgroup_Support" target="_blank" className="bg-[#0088cc] hover:bg-[#0077b3] transition-colors px-10 py-4 rounded-full font-bold text-lg text-white flex items-center gap-3 shadow-lg shadow-[#0088cc]/30">
                            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.895-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.897-.666 3.522-1.533 5.87-2.545 7.045-3.036 3.35-1.39 4.047-1.634 4.502-1.644.1 0 .324.023.47.14.12.097.153.228.166.323.015.098.03.282.013.475z"/></svg>
                            Связаться в Telegram
                        </a>
                    </div>

                    {/*  Карточки контактов  */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto">
                        {/*  Email  */}
                        <a href="mailto:next-tech@mail.ru" className="glass rounded-2xl p-6 flex items-center gap-5 hover:bg-white/5 transition-colors text-left reveal delay-1">
                            <div className="w-12 h-12 rounded-full bg-[#f97316] flex items-center justify-center text-white font-bold text-xl shrink-0">
                                @
                            </div>
                            <div>
                                <div className="text-sm text-gray-400 mb-1">Email</div>
                                <div className="text-lg font-bold text-white">next-tech@mail.ru</div>
                            </div>
                        </a>
                        
                        {/*  Телефон  */}
                        <a href="tel:+79969795488" className="glass rounded-2xl p-6 flex items-center gap-5 hover:bg-white/5 transition-colors text-left reveal delay-2">
                            <div className="w-12 h-12 rounded-full bg-[#f97316] flex items-center justify-center text-white text-xl shrink-0">
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>
                            </div>
                            <div>
                                <div className="text-sm text-gray-400 mb-1">Телефон</div>
                                <div className="text-lg font-bold text-white">+7 996 979 54 88</div>
                            </div>
                        </a>
                    </div>
                    
                </div>
            </div>
        </div>
    </section>

    {/*  ===================== ПОДВАЛ =====================  */}
    <footer className="border-t border-white/8 py-12">
        <div className="container mx-auto px-6 max-w-7xl">
            <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl btn-primary flex items-center justify-center">
                            <span className="text-white font-black text-sm">N</span>
                        </div>
                        <span className="text-xl font-black tracking-tight">Next <span className="gradient-text">Gadget</span></span>
                    </div>
                    <div className="text-sm text-gray-400">
                        <p>Москва, ул. Тверская, 1</p>
                        <p><a href="tel:+79969795488" className="hover:text-white transition-colors">+7 996 979 54 88</a></p>
                        <p><a href="mailto:next-tech@mail.ru" className="hover:text-white transition-colors">next-tech@mail.ru</a></p>
                    </div>
                </div>
                <div className="flex flex-col items-end gap-4">
                    <div className="flex items-center gap-8 text-sm text-gray-500">
                        <a href="#features" className="hover:text-white transition-colors">Возможности</a>
                        <a href="#choose" className="hover:text-white transition-colors">Гаджеты</a>
                        <a href="#why" className="hover:text-white transition-colors">О нас</a>
                    </div>
                    <div className="text-sm text-gray-600">
                        © 2026 Next Gadget. Все права защищены.
                    </div>
                </div>
            </div>
        </div>
    </footer>

    

    </>
  );
}
