import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import encode_rfc2231

def send_email(**kwargs):
    '''
    Функция для отправки почтовых сообщений, параметры:
    to_email, subject, body, attachment_path
    '''
    
    try:
        parametrs = json.loads(os.environ['smtp_parameters'])
    
        smtp_host =parametrs['smtp_host' ]
        smtp_port =parametrs['smtp_port' ]
        login     =parametrs['login'     ]
        password  =parametrs['password'  ]
        from_email=parametrs['from_email']    
    
    except Exception as e:      
        print(parametrs)
        return(None)
    
    to_email        = kwargs['to_email']
    subject         = kwargs['subject']
    body            = kwargs['body']
    attachment_path = kwargs.get('attachment_path', '')
        
    # Создание объекта письма
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    # Добавление текста письма
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    # Добавление вложения
    if attachment_path:
        with open(attachment_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())

        # Кодировка вложения в base64
        encoders.encode_base64(part)

        # Установка имени файла вложения
        filename = attachment_path.split('/')[-1]  # Извлечение имени файла из пути
        encoded_filename = encode_rfc2231(filename, 'utf-8')  # Кодировка имени файла
        part.add_header(
            'Content-Disposition',
            f'attachment; filename*={encoded_filename}'
        )

        # Прикрепление вложения к письму
        msg.attach(part)

    # Отправка письма через SMTP-сервер
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        #server.starttls()  # Для шифрования соединения (используется порт 587)
        server.login(login, password)
        server.sendmail(from_email, to_email, msg.as_string())
        return(1)
    except Exception as e:
        print(e)
        return(0)
    finally:
        server.quit()