# 🤖 Pharmastic Bot - WhatsApp Pharmacy Assistant

An AI-powered WhatsApp chatbot for pharmacy assistance, built with FastAPI and GROQ AI.

---

## 🌟 Features

- ✅ **WhatsApp Integration** - Receive and respond to WhatsApp messages
- ✅ **AI-Powered Responses** - Uses GROQ AI (Llama 3.3) for intelligent conversations
- ✅ **Webhook Support** - Real-time message handling via Meta WhatsApp API
- ✅ **Cloud Deployment Ready** - Configured for Render deployment
- ✅ **MongoDB Integration** - Store user data and conversations
- ✅ **Easy Setup** - Simple environment variable configuration

---

## 📋 Quick Start

### Prerequisites

- Python 3.11+
- WhatsApp Business API access (Meta Developer account)
- GROQ API key (free at https://console.groq.com)
- MongoDB Atlas account (free tier available)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Pharmastic-Bot.git
   cd Pharmastic-Bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   WHATSAPP_TOKEN=your_whatsapp_token
   PHONE_NUMBER_ID=your_phone_number_id
   VERIFY_TOKEN=teamsamay123
   GROQ_API_KEY=your_groq_api_key
   MONGODB_URL=your_mongodb_connection_string
   DATABASE_NAME=pharmastic_bot
   ```

4. **Run the application**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Test locally**
   - Open: http://localhost:8000
   - You should see: `{"status":"WhatsApp Pharmacy Bot Running"}`

---

## 🚀 Deployment to Render

### Quick Deployment Steps

1. **Push code to GitHub**
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. **Deploy to Render**
   - Go to https://dashboard.render.com
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure settings (see deployment guide)
   - Add environment variables
   - Click "Create Web Service"

3. **Configure WhatsApp Webhook**
   - Go to Meta Developer Console
   - Navigate to: WhatsApp → Configuration
   - Set Callback URL: `https://your-app.onrender.com/webhook`
   - Set Verify Token: `teamsamay123`
   - Subscribe to `messages` field

### 📚 Detailed Guides

For complete step-by-step instructions, see:

- **[RENDER_DEPLOYMENT_GUIDE.md](RENDER_DEPLOYMENT_GUIDE.md)** - Full deployment guide for Render
- **[WEBHOOK_SETUP_GUIDE.md](WEBHOOK_SETUP_GUIDE.md)** - WhatsApp webhook configuration
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Checklist to track your progress

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `WHATSAPP_TOKEN` | WhatsApp API access token | `EAASG5K6pZBN4...` |
| `PHONE_NUMBER_ID` | WhatsApp Business Phone Number ID | `1050052344846616` |
| `VERIFY_TOKEN` | Custom webhook verification token | `teamsamay123` |
| `GROQ_API_KEY` | GROQ API key for AI responses | `gsk_F7NgWYsb...` |
| `MONGODB_URL` | MongoDB connection string | `mongodb+srv://...` |
| `DATABASE_NAME` | Database name | `pharmastic_bot` |

---

## 🧪 Testing

### Test Endpoints

1. **Health Check**
   ```
   GET https://your-app.onrender.com/
   ```
   Response: `{"status":"WhatsApp Pharmacy Bot Running"}`

2. **Webhook Verification**
   ```
   GET https://your-app.onrender.com/webhook?hub.verify_token=teamsamay123&hub.challenge=test
   ```
   Response: `test`

3. **Send Test Message**
   ```
   GET https://your-app.onrender.com/test-send?phone=919876543210&message=Hello
   ```

### WhatsApp Testing

1. Send a message to your WhatsApp Business number
2. Bot should reply within 2-5 seconds
3. Check Render logs for debugging

---

## 📁 Project Structure

```
Pharmastic-Bot/
├── app/
│   └── main.py              # FastAPI application
├── static/                  # Static files (if any)
├── .env                     # Environment variables (local only)
├── .gitignore              # Git ignore rules
├── Procfile                # Render deployment config
├── render.yaml             # Render service configuration
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── RENDER_DEPLOYMENT_GUIDE.md    # Deployment guide
├── WEBHOOK_SETUP_GUIDE.md        # Webhook setup guide
└── DEPLOYMENT_CHECKLIST.md       # Deployment checklist
```

---

## 🔍 API Endpoints

### `GET /`
Health check endpoint

**Response:**
```json
{"status": "WhatsApp Pharmacy Bot Running"}
```

### `GET /webhook`
Webhook verification endpoint (used by Meta)

**Query Parameters:**
- `hub.mode` - Should be "subscribe"
- `hub.verify_token` - Your verify token
- `hub.challenge` - Random number to echo back

### `POST /webhook`
Receive WhatsApp messages

**Request Body:** WhatsApp webhook payload

**Response:**
```json
{"status": "ok"}
```

### `GET /test-send`
Test message sending

**Query Parameters:**
- `phone` - Phone number (with country code)
- `message` - Message to send

---

## 🐛 Troubleshooting

### Common Issues

1. **Webhook Verification Failed**
   - Check if Render app is running
   - Verify `VERIFY_TOKEN` matches in both places
   - Test webhook manually in browser

2. **Bot Not Replying**
   - Check Render logs for errors
   - Verify `WHATSAPP_TOKEN` is valid
   - Ensure subscribed to `messages` field

3. **App Keeps Sleeping (Free Tier)**
   - Use UptimeRobot to ping app every 5 minutes
   - Or upgrade to paid plan ($7/month)

For more troubleshooting, see [RENDER_DEPLOYMENT_GUIDE.md](RENDER_DEPLOYMENT_GUIDE.md)

---

## 📊 Monitoring

### Render Logs
- Go to Render Dashboard → Your Service → Logs
- View real-time logs of incoming messages

### Meta Webhook Logs
- Go to Meta Developer Console → WhatsApp → Configuration
- Click "View Logs" to see webhook delivery status

### Uptime Monitoring
- Use UptimeRobot (free): https://uptimerobot.com
- Ping your app every 5 minutes to prevent sleeping

---

## 🔐 Security

- ✅ Never commit `.env` file to GitHub
- ✅ Use environment variables for all secrets
- ✅ Regenerate tokens if accidentally exposed
- ✅ Enable 2FA on all accounts
- ✅ Regularly update dependencies

---

## 🛠️ Tech Stack

- **Backend:** FastAPI (Python)
- **AI:** GROQ (Llama 3.3-70B)
- **Database:** MongoDB Atlas
- **Messaging:** WhatsApp Business API (Meta)
- **Deployment:** Render
- **Version Control:** Git/GitHub

---

## 📈 Future Enhancements

- [ ] Add medicine order processing
- [ ] Implement user authentication
- [ ] Add prescription upload support
- [ ] Multi-language support (Hindi, English)
- [ ] Order tracking and history
- [ ] Payment integration
- [ ] Admin dashboard

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🆘 Support

If you encounter issues:

1. Check the deployment guides
2. Review Render logs
3. Check Meta webhook logs
4. Open an issue on GitHub

---

## 🎉 Acknowledgments

- **GROQ** - For free and fast AI API
- **Meta** - For WhatsApp Business API
- **Render** - For easy deployment platform
- **MongoDB Atlas** - For free cloud database

---

**Made with ❤️ for better pharmacy assistance**

---

## 📞 Contact

For questions or support, please open an issue on GitHub.

---

**🚀 Ready to deploy? Start with [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)!**