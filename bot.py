import logging
import sqlite3
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Bot token and channel IDs configuration
TOKEN = ''
CHANNEL_IDS = ['-1001796172710', '-1001755556743']  # Lista de canales
WELCOME_PHOTO = 'src/image.jpg'  # Ruta a la foto de bienvenida
ADMIN_CHAT_ID = 1618347551  # Tu propio chat ID (cambié de string a int para uso directo)

# Database setup
conn = sqlite3.connect('subscriptions.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                  (user_id INTEGER PRIMARY KEY, 
                   expiration_date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS pending_payments 
                  (user_id INTEGER PRIMARY KEY, 
                   subscription_type TEXT, 
                   photo_file_id TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS trial_subscriptions 
                  (user_id INTEGER PRIMARY KEY)''')  # Tabla para trial subscriptions
conn.commit()

# Duración de la suscripción de prueba (30 minutos)
TRIAL_DURATION = timedelta(minutes=30)

# Start command handler
async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = f'''
<b>¡Bienvenido!</b>

<i>Este bot le permite suscribirse a canales de multimedia de pago</i>
» Usa /subscribe para suscribirte.
» Usa /trial_subscribe para obtener una suscripción de prueba.

<b>👨🏻‍💻Admin:</b> <a href="tg://user?id={ADMIN_CHAT_ID}">KeimaSenpai</a>
    '''
    await context.bot.send_photo(chat_id=update.message.chat_id, photo=open(WELCOME_PHOTO, 'rb'), caption=welcome_message, parse_mode=ParseMode.HTML)

# Subscribe command handler
async def subscribe(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Semanal 10 CUP", callback_data='subscription_weekly')],
        [InlineKeyboardButton("Mensual 25 CUP", callback_data='subscription_monthly')],
        [InlineKeyboardButton("Anual 50 CUP", callback_data='subscription_annual')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('<b>Selecciona el tipo de suscripción:</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# Trial subscribe command handler
async def trial_subscribe(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Verificar si el usuario ya ha solicitado la suscripción de prueba
    cursor.execute('SELECT user_id FROM trial_subscriptions WHERE user_id = ?', (user_id,))
    existing_trial_subscription = cursor.fetchone()

    if existing_trial_subscription:
        await update.message.reply_text('Ya has solicitado la suscripción de prueba anteriormente.')
        return

    # Calcular la fecha de vencimiento para la suscripción de prueba
    expiration_date = datetime.now() + TRIAL_DURATION

    # Guardar la suscripción en la base de datos
    cursor.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiration_date) VALUES (?, ?)',
                   (user_id, expiration_date.isoformat()))
    conn.commit()

    # Registrar la solicitud de suscripción de prueba
    cursor.execute('INSERT INTO trial_subscriptions (user_id) VALUES (?)', (user_id,))
    conn.commit()

    # Generar el enlace de invitación al canal con un límite de miembros
    try:
        for channel_id in CHANNEL_IDS:
            invite_link_object = await context.bot.create_chat_invite_link(chat_id=channel_id, member_limit=1)
            invite_link = invite_link_object.invite_link

            # Enviar el enlace de invitación al usuario
            await context.bot.send_message(chat_id=user_id, text=f"""
<b>Enlace de invitación único al canal:</b>
{invite_link}
<b>Suscripción de prueba activada por 10 minutos.</b>
""",parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f'Error al generar el enlace de invitación: {str(e)}')
        await update.message.reply_text('Ha ocurrido un error al generar el enlace de invitación. Inténtalo nuevamente más tarde.')

# Callback query handler for subscription type
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data.split('_')
    action = data[0]
    if action == 'subscription':
        subscription_type = data[1]
        context.user_data['subscription_type'] = subscription_type
        await query.message.reply_html('''
<b>Por favor, envía una foto de la transferencia.</b>
<b>💳Tarjeta:</b> <code>9227 9598 7554 6900</code>
                                       
''')
    elif action == 'approve':
        user_id = int(data[1])
        subscription_type = data[2]
        now = datetime.now()
        if subscription_type == 'weekly':
            expiration_date = now + timedelta(weeks=1)
        elif subscription_type == 'monthly':
            expiration_date = now + timedelta(weeks=4)
        elif subscription_type == 'annual':
            expiration_date = now + timedelta(weeks=52)

        cursor.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiration_date) VALUES (?, ?)',
                       (user_id, expiration_date.isoformat()))
        conn.commit()

        # Add user to all listed channels
        for channel_id in CHANNEL_IDS:
            invite_link_object = await context.bot.create_chat_invite_link(chat_id=channel_id, member_limit=1)
            invite_link = invite_link_object.invite_link
            await context.bot.send_message(chat_id=user_id, text=f"""
<b>Enlace de invitación único al canal:</b>
{invite_link}
<blockquote expandable>Muchas gracias por tu suscripción. Cualquier problema que tengas, contacta con el admin. Recibirás una notificación un día antes del vencimiento de tu suscripción.</blockquote>
""", parse_mode=ParseMode.HTML)

        await query.edit_message_caption(caption=f'Suscripción aprobada: {subscription_type}')
        await context.bot.send_message(chat_id=user_id, text=f'Tu suscripción de tipo {subscription_type} ha sido aprobada.')

    elif action == 'reject':
        user_id = int(data[1])
        await query.edit_message_caption(caption='Suscripción rechazada.')
        await context.bot.send_message(chat_id=user_id, text='Tu suscripción ha sido rechazada.')

# Photo handler for payment verification
async def photo_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if 'subscription_type' not in context.user_data:
        await update.message.reply_text('Primero selecciona el tipo de suscripción usando /subscribe.')
        return

    subscription_type = context.user_data['subscription_type']
    photo_file_id = update.message.photo[-1].file_id

    # Send approval request to admin
    keyboard = [
        [InlineKeyboardButton("Aprobar", callback_data=f"approve_{user_id}_{subscription_type}")],
        [InlineKeyboardButton("Rechazar", callback_data=f"reject_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=photo_file_id,
                                 caption=f'Nueva solicitud de suscripción: {subscription_type}',
                                 reply_markup=reply_markup)
    await update.message.reply_text('Foto recibida. Espera la aprobación.')

# Periodic job to check subscriptions
async def check_subscriptions(context: CallbackContext) -> None:
    now = datetime.now()
    cursor.execute('SELECT user_id FROM subscriptions WHERE expiration_date < ?', (now.isoformat(),))
    expired_users = cursor.fetchall()

    for (user_id,) in expired_users:
        for channel_id in CHANNEL_IDS:
            await context.bot.ban_chat_member(channel_id, user_id)
        cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
        await context.bot.send_message(chat_id=user_id, text='Has sido sacado de los canales')

    conn.commit()

# Daily job to send reminders
async def send_reminders(context: CallbackContext) -> None:
    now = datetime.now()
    reminder_date = (now + timedelta(days=1)).isoformat()
    cursor.execute('SELECT user_id FROM subscriptions WHERE expiration_date LIKE ?', (reminder_date + '%',))
    users_to_remind = cursor.fetchall()

    for (user_id,) in users_to_remind:
        await context.bot.send_message(chat_id=user_id, text='Tu suscripción expira mañana. Si deseas renovarla, por favor realiza el pago correspondiente.')

# Main function to start the bot
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("trial_subscribe", trial_subscribe))  # Nuevo comando
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(CallbackQueryHandler(button))

    job_queue = application.job_queue
    job_queue.run_repeating(check_subscriptions, interval=30, first=0)  # Verificar suscripciones cada hora
    job_queue.run_daily(send_reminders, time=time(9, 0))  # Recordatorios diarios a las 9 AM

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
