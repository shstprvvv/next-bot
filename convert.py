import re

def convert_html_to_jsx(html_path, jsx_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract body content
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_match:
        print("Body not found")
        return
    
    body_content = body_match.group(1)

    # Remove script tags
    body_content = re.sub(r'<script.*?</script>', '', body_content, flags=re.DOTALL)

    # Convert class to className
    jsx = body_content.replace('class="', 'className="')

    # Convert inline styles
    # style="width:0%" -> style={{ width: '0%' }}
    # style="padding:1.5px; border-radius:28px; background: linear-gradient(...); -webkit-mask: ...; -webkit-mask-composite: xor; mask-composite: exclude;"
    # Let's just use manual replacements for the known styles since there are only a few complex ones.
    
    jsx = jsx.replace('style="width:0%"', "style={{ width: '0%' }}")
    
    style1 = 'style="padding:1.5px; border-radius:28px; background: linear-gradient(135deg, rgba(59,130,246,0.6), rgba(99,102,241,0.2), rgba(255,255,255,0.04)); -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0); -webkit-mask-composite: xor; mask-composite: exclude;"'
    jsx = jsx.replace(style1, "style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(59,130,246,0.6), rgba(99,102,241,0.2), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}")

    style2 = 'style="background: linear-gradient(135deg,#3b82f6,#6366f1); box-shadow: 0 4px 15px rgba(59,130,246,0.4);"'
    jsx = jsx.replace(style2, "style={{ background: 'linear-gradient(135deg,#3b82f6,#6366f1)', boxShadow: '0 4px 15px rgba(59,130,246,0.4)' }}")

    style3 = 'style="background:rgba(59,130,246,0.12); border:1px solid rgba(59,130,246,0.2)"'
    jsx = jsx.replace(style3, "style={{ background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.2)' }}")

    style4 = 'style="background:linear-gradient(135deg,#60a5fa,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text"'
    jsx = jsx.replace(style4, "style={{ background: 'linear-gradient(135deg,#60a5fa,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}")

    style5 = 'style="background:linear-gradient(135deg,#7c3aed,#a855f7)"'
    jsx = jsx.replace(style5, "style={{ background: 'linear-gradient(135deg,#7c3aed,#a855f7)' }}")

    style6 = 'style="margin-top: -12px;"'
    jsx = jsx.replace(style6, "style={{ marginTop: '-12px' }}")

    style7 = 'style="padding:1.5px; border-radius:28px; background: linear-gradient(135deg, rgba(139,92,246,0.7), rgba(168,85,247,0.3), rgba(255,255,255,0.04)); -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0); -webkit-mask-composite: xor; mask-composite: exclude;"'
    jsx = jsx.replace(style7, "style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(139,92,246,0.7), rgba(168,85,247,0.3), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}")

    style8 = 'style="background: linear-gradient(135deg,#7c3aed,#a855f7); box-shadow: 0 4px 15px rgba(139,92,246,0.5);"'
    jsx = jsx.replace(style8, "style={{ background: 'linear-gradient(135deg,#7c3aed,#a855f7)', boxShadow: '0 4px 15px rgba(139,92,246,0.5)' }}")

    style9 = 'style="background:rgba(139,92,246,0.12); border:1px solid rgba(139,92,246,0.25)"'
    jsx = jsx.replace(style9, "style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.25)' }}")

    style10 = 'style="background:linear-gradient(135deg,#a78bfa,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text"'
    jsx = jsx.replace(style10, "style={{ background: 'linear-gradient(135deg,#a78bfa,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}")

    style11 = 'style="background:linear-gradient(135deg,#0065ff,#005bde)"'
    jsx = jsx.replace(style11, "style={{ background: 'linear-gradient(135deg,#0065ff,#005bde)' }}")

    style12 = 'style="padding:1.5px; border-radius:28px; background: linear-gradient(135deg, rgba(16,185,129,0.6), rgba(5,150,105,0.2), rgba(255,255,255,0.04)); -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0); -webkit-mask-composite: xor; mask-composite: exclude;"'
    jsx = jsx.replace(style12, "style={{ padding: '1.5px', borderRadius: '28px', background: 'linear-gradient(135deg, rgba(16,185,129,0.6), rgba(5,150,105,0.2), rgba(255,255,255,0.04))', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}")

    style13 = 'style="background: linear-gradient(135deg,#059669,#10b981); box-shadow: 0 4px 15px rgba(16,185,129,0.4);"'
    jsx = jsx.replace(style13, "style={{ background: 'linear-gradient(135deg,#059669,#10b981)', boxShadow: '0 4px 15px rgba(16,185,129,0.4)' }}")

    style14 = 'style="background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.25)"'
    jsx = jsx.replace(style14, "style={{ background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.25)' }}")

    style15 = 'style="background:linear-gradient(135deg,#34d399,#10b981);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text"'
    jsx = jsx.replace(style15, "style={{ background: 'linear-gradient(135deg,#34d399,#10b981)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}")


    # Close self-closing tags
    jsx = re.sub(r'<img([^>]*?)(?<!/)>', r'<img\1 />', jsx)
    jsx = re.sub(r'<path([^>]*?)(?<!/)>', r'<path\1 />', jsx)
    
    # Fix SVG attributes
    jsx = jsx.replace('stroke-linecap', 'strokeLinecap')
    jsx = jsx.replace('stroke-linejoin', 'strokeLinejoin')
    jsx = jsx.replace('stroke-width', 'strokeWidth')
    jsx = jsx.replace('viewBox', 'viewBox') # already correct, just ensuring
    
    # Fix onerror
    jsx = re.sub(r'onerror="[^"]*"', '', jsx)

    # Wrap in React component
    react_code = """'use client';

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
""" + jsx + """
    </>
  );
}
"""
    # Fix HTML comments
    react_code = re.sub(r'<!--(.*?)-->', r'{/* \1 */}', react_code)

    with open(jsx_path, 'w', encoding='utf-8') as f:
        f.write(react_code)

convert_html_to_jsx('landing.html', 'page_new.tsx')
