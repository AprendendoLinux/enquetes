import smtplib
import ssl
import os
import logging
import traceback
from email.message import EmailMessage

# --- CONFIGURAÇÃO DE LOGS ---
# Isso garante que os logs apareçam no 'docker logs'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_utils")

# Configurações de SMTP
SMTP_HOST = os.getenv("SMTP_HOST")
# Converte para inteiro, padrão 587 se não definido
SMTP_PORT = int(os.getenv("SMTP_PORT", 587)) 
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")

def _get_html_template(base_url: str, title: str, body_content: str, action_url: str = None, action_text: str = None):
    clean_base_url = base_url.rstrip("/")
    logo_url = f"{clean_base_url}/static/logo.png"
    
    button_html = ""
    if action_url and action_text:
        button_html = f"""
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" class="btn btn-primary" style="margin: 0 auto;">
            <tbody>
            <tr>
                <td align="center">
                    <a href="{action_url}" target="_blank" style="background-color: #212529; border-radius: 50px; color: #ffffff; display: inline-block; padding: 14px 30px; text-decoration: none; font-weight: bold; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">{action_text}</a>
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
    </head>
    <body style="background-color: #f6f6f6; font-family: sans-serif; font-size: 14px; line-height: 1.4; margin: 0; padding: 0;">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="width: 100%; background-color: #f6f6f6;">
        <tr>
            <td>&nbsp;</td>
            <td style="display: block; margin: 0 auto !important; max-width: 580px; padding: 10px; width: 580px;">
            <div style="box-sizing: border-box; display: block; margin: 0 auto; max-width: 580px; padding: 10px;">
                <table role="presentation" style="background: #ffffff; border-radius: 12px; width: 100%; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
                    <tr>
                        <td style="background-color: #212529; padding: 30px 0; text-align: center;">
                            <img src="{logo_url}" alt="Logo" width="100" style="width: 100px; height: auto; display: block; margin: 0 auto; filter: brightness(0) invert(1);" />
                            <div style="color: white; font-size: 18px; margin-top: 10px; letter-spacing: 1px; text-transform: uppercase; font-weight: 700; text-align: center;">Sistema de Enquetes</div>
                        </td>
                    </tr>
                    <tr>
                        <td style="box-sizing: border-box; padding: 40px 30px; text-align: center;">
                            <h1 style="color: #000000; font-size: 24px; margin-bottom: 25px; text-align: center;">{title}</h1>
                            <p style="font-family: sans-serif; font-size: 16px; font-weight: normal; margin: 0; margin-bottom: 20px; color: #555555; text-align: center;">{body_content}</p>
                            <br>
                            {button_html}
                            <br><br>
                            <p style="color: #999999; font-size: 12px; text-align: center;">Se você não solicitou esta ação, ignore este e-mail.</p>
                        </td>
                    </tr>
                </table>
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
    msg['Subject'] = "Confirme seu cadastro"
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    
    html_content = _get_html_template(
        base_url=clean_base_url,
        title="Bem-vindo(a)!",
        body_content="Confirme seu e-mail para ativar sua conta.",
        action_url=link,
        action_text="Confirmar Agora"
    )
    msg.set_content(f"Link: {link}")
    msg.add_alternative(html_content, subtype='html')
    _send_email(msg, to_email)

def send_reset_password_email(to_email: str, token: str, base_url: str):
    clean_base_url = base_url.rstrip("/")
    link = f"{clean_base_url}/auth/reset-password/{token}"
    
    msg = EmailMessage()
    msg['Subject'] = "Recuperação de Senha"
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    
    html_content = _get_html_template(
        base_url=clean_base_url,
        title="Esqueceu sua senha?",
        body_content="Clique abaixo para redefinir.",
        action_url=link,
        action_text="Redefinir Senha"
    )
    msg.set_content(f"Link: {link}")
    msg.add_alternative(html_content, subtype='html')
    _send_email(msg, to_email)

def _send_email(msg, to_email):
    logger.info("="*40)
    logger.info(f" INICIANDO PROCESSO DE ENVIO: {to_email}")
    logger.info(f" Config: HOST={SMTP_HOST} | PORT={SMTP_PORT} | USER={SMTP_USER}")
    
    try:
        # 1. CONEXÃO
        logger.info("[1/6] Conectando ao servidor SMTP...")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.set_debuglevel(1) # Ativa o debug nativo do SMTP (mostra conversa com o servidor)
        
        # 2. EHLO INICIAL
        logger.info("[2/6] Enviando EHLO...")
        server.ehlo()

        # 3. STARTTLS (CRIPTOGRAFIA)
        # Lógica: Se for porta 587 OU se o servidor anunciar suporte a STARTTLS, ativa.
        if SMTP_PORT == 587 or server.has_extn("STARTTLS"):
            logger.info("[3/6] Iniciando STARTTLS...")
            context = ssl.create_default_context()
            
            # --- NOTA DE DEBUG: Se tiver erro de certificado (SSL), descomente as linhas abaixo ---
            # context.check_hostname = False
            # context.verify_mode = ssl.CERT_NONE
            
            server.starttls(context=context)
            logger.info("[3/6] STARTTLS concluído. Reenviando EHLO...")
            server.ehlo()
        else:
            logger.info("[3/6] Pulo do STARTTLS (Porta não é 587 e servidor não pediu).")

        # 4. AUTENTICAÇÃO
        if SMTP_USER and SMTP_PASSWORD:
            logger.info("[4/6] Credenciais detectadas. Tentando LOGIN...")
            server.login(SMTP_USER, SMTP_PASSWORD)
            logger.info("[4/6] Login realizado com SUCESSO.")
        else:
            logger.info("[4/6] Sem credenciais configuradas. Modo RELAY (Anônimo/IP).")

        # 5. ENVIO
        logger.info("[5/6] Enviando a mensagem...")
        server.send_message(msg)
        logger.info("[6/6] Mensagem ACEITA pelo servidor.")

        server.quit()
        logger.info(" EMAIL ENVIADO COM SUCESSO!")
        logger.info("="*40)
        
    except Exception as e:
        logger.error("!!!" + "="*30 + "!!!")
        logger.error(" ERRO FATAL NO ENVIO DE E-MAIL")
        logger.error(f" Mensagem de erro: {e}")
        logger.error(" Stack Trace:")
        logger.error(traceback.format_exc())
        logger.error("!!!" + "="*30 + "!!!")