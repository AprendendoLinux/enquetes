import smtplib
import os
from email.message import EmailMessage

# Configurações de SMTP
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")

def _get_html_template(base_url: str, title: str, body_content: str, action_url: str = None, action_text: str = None):
    """
    Gera um HTML responsivo, com logo, rodapé LGPD e TEXTO CENTRALIZADO.
    """
    clean_base_url = base_url.rstrip("/")
    logo_url = f"{clean_base_url}/static/logo.png"
    
    # Botão de ação (Centralizado)
    button_html = ""
    if action_url and action_text:
        button_html = f"""
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" class="btn btn-primary" style="margin: 0 auto;">
            <tbody>
            <tr>
                <td align="center">
                <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                    <tbody>
                    <tr>
                        <td align="center">
                            <a href="{action_url}" target="_blank" style="background-color: #212529; border-radius: 50px; color: #ffffff; display: inline-block; padding: 14px 30px; text-decoration: none; font-weight: bold; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">{action_text}</a>
                        </td>
                    </tr>
                    </tbody>
                </table>
                </td>
            </tr>
            </tbody>
        </table>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <title>{title}</title>
        <style>
        /* Reset de estilos */
        img {{ border: none; -ms-interpolation-mode: bicubic; max-width: 100%; }}
        body {{ background-color: #f6f6f6; font-family: sans-serif; -webkit-font-smoothing: antialiased; font-size: 14px; line-height: 1.4; margin: 0; padding: 0; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
        table {{ border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; }}
        table td {{ font-family: sans-serif; font-size: 14px; vertical-align: top; }}

        /* Estilos do Container */
        .body {{ background-color: #f6f6f6; width: 100%; }}
        .container {{ display: block; margin: 0 auto !important; max-width: 580px; padding: 10px; width: 580px; }}
        .content {{ box-sizing: border-box; display: block; margin: 0 auto; max-width: 580px; padding: 10px; }}

        /* Estilos do Cartão Principal */
        .main {{ background: #ffffff; border-radius: 12px; width: 100%; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }}
        .wrapper {{ box-sizing: border-box; padding: 40px 30px; text-align: center; }} /* padding aumentado e text-align center */
        
        .footer {{ clear: both; margin-top: 10px; text-align: center; width: 100%; }}
        .footer td, .footer p, .footer span, .footer a {{ color: #999999; font-size: 12px; text-align: center; }}

        /* Tipografia Centralizada */
        h1, h2, h3 {{ color: #000000; font-family: sans-serif; font-weight: 700; line-height: 1.4; margin: 0; margin-bottom: 20px; text-align: center; }}
        h1 {{ font-size: 24px; margin-bottom: 25px; }}
        p, ul, ol {{ font-family: sans-serif; font-size: 16px; font-weight: normal; margin: 0; margin-bottom: 20px; color: #555555; text-align: center; }}
        
        /* Header Personalizado */
        .header-brand {{ background-color: #212529; padding: 30px 0; text-align: center; }}
        .header-title {{ color: white; font-size: 18px; margin-top: 10px; letter-spacing: 1px; text-transform: uppercase; font-weight: 700; text-align: center; }}

        /* Responsividade Mobile */
        @media only screen and (max-width: 620px) {{
            table[class=body] h1 {{ font-size: 26px !important; margin-bottom: 15px !important; }}
            table[class=body] p, table[class=body] ul, table[class=body] ol, table[class=body] td, table[class=body] span, table[class=body] a {{ font-size: 16px !important; }}
            table[class=body] .wrapper {{ padding: 25px !important; }}
            table[class=body] .content {{ padding: 0 !important; }}
            table[class=body] .container {{ padding: 0 !important; width: 100% !important; }}
            table[class=body] .main {{ border-radius: 0 !important; }}
            table[class=body] .btn table {{ width: 100% !important; }}
            table[class=body] .btn a {{ width: 100% !important; display: block !important; }} /* Botão full width no mobile */
        }}
        </style>
    </head>
    <body>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" class="body">
        <tr>
            <td>&nbsp;</td>
            <td class="container">
            <div class="content">

                <table role="presentation" class="main">
                    
                    <tr>
                        <td class="header-brand">
                            <img src="{logo_url}" alt="Logo" width="100" style="width: 100px; height: auto; display: block; margin: 0 auto; filter: brightness(0) invert(1);" />
                            <div class="header-title">Sistema de Enquetes</div>
                        </td>
                    </tr>

                    <tr>
                        <td class="wrapper">
                        <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                            <tr>
                            <td align="center">
                                <h1>{title}</h1>
                                <p>{body_content}</p>
                                <br>
                                {button_html}
                                <br><br>
                                <p class="text-muted" style="font-size: 14px;">Se você não solicitou esta ação, por favor ignore este e-mail.</p>
                            </td>
                            </tr>
                        </table>
                        </td>
                    </tr>
                </table>

                <div class="footer">
                <table role="presentation" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                    <td class="content-block">
                        <span class="apple-link"><strong>Sistema de Enquetes Inteligente</strong></span>
                        <br> Todos os direitos reservados &copy; 2026.
                    </td>
                    </tr>
                    <tr>
                    <td class="content-block" style="padding-top: 15px;">
                        <strong>Aviso de Privacidade (LGPD):</strong><br>
                        Respeitamos sua privacidade e protegemos seus dados pessoais conforme a Lei Geral de Proteção de Dados. 
                        Este e-mail é transacional e essencial para a segurança da sua conta.
                    </td>
                    </tr>
                </table>
                </div>

            </div>
            </td>
            <td>&nbsp;</td>
        </tr>
        </table>
    </body>
    </html>
    """

def send_verification_email(to_email: str, token: str, base_url: str):
    clean_base_url = base_url.rstrip("/")
    link = f"{clean_base_url}/auth/verify/{token}"
    
    msg = EmailMessage()
    msg['Subject'] = "Confirme seu cadastro - Sistema de Enquetes"
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    
    body_text = "Estamos muito felizes em ter você conosco! Para garantir a segurança da sua conta e começar a criar enquetes, por favor, confirme seu endereço de e-mail clicando no botão abaixo."
    
    html_content = _get_html_template(
        base_url=clean_base_url,
        title="Bem-vindo(a)!",
        body_content=body_text,
        action_url=link,
        action_text="Confirmar E-mail Agora"
    )
    
    msg.set_content(f"Clique no link para confirmar: {link}")
    msg.add_alternative(html_content, subtype='html')
    
    _send_email(msg, to_email)

def send_reset_password_email(to_email: str, token: str, base_url: str):
    clean_base_url = base_url.rstrip("/")
    link = f"{clean_base_url}/auth/reset-password/{token}"
    
    msg = EmailMessage()
    msg['Subject'] = "Recuperação de Senha - Sistema de Enquetes"
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    
    body_text = "Recebemos uma solicitação para redefinir a senha da sua conta. Se foi você, clique no botão abaixo para criar uma nova senha. Este link expira em 30 minutos."
    
    html_content = _get_html_template(
        base_url=clean_base_url,
        title="Esqueceu sua senha?",
        body_content=body_text,
        action_url=link,
        action_text="Redefinir Minha Senha"
    )
    
    msg.set_content(f"Para redefinir sua senha, acesse: {link}")
    msg.add_alternative(html_content, subtype='html')
    
    _send_email(msg, to_email)

def _send_email(msg, to_email):
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"E-mail enviado para {to_email}")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")