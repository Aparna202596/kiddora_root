🧸 Kiddora – Kids E-Commerce Platform

Kiddora is a monolithic Django-based e-commerce web application designed for selling kids’ clothing (newborn to 15 years). It provides a complete shopping ecosystem including product browsing, cart management, secure payments, and a powerful admin dashboard.

The project focuses on clean architecture, scalable backend design, and a smooth user experience.

🚀 Tech Stack
Backend
Python
Django
Django ORM
PostgreSQL
Frontend
HTML5, CSS3
Bootstrap
JavaScript (AJAX)
Authentication & Security
Email OTP verification
Social login (SSO)
Password reset flow
Session & CSRF protection
Role-based access control
Storage & Deployment
Cloudinary (media & static files)
AWS EC2 (deployment)
Gunicorn + Nginx
Payments
PayPal Sandbox
Cash on Delivery (COD)
✨ Core Features
👨‍💼 Admin Panel
User, product & category management
Order tracking & status updates
Return & cancellation handling
Inventory management
Coupon & offer system
Sales analytics overview
Soft delete with data recovery support
Search, filter & pagination support
👤 User Features
Secure signup/login with OTP
Social authentication
Profile & address management
Wishlist & shopping cart (AJAX-based)
Product search, filtering & sorting
Checkout with multiple payment options
Order tracking & invoice download
Return & refund system
💰 Business Logic
Dynamic discount engine:
Product offers
Category offers
Coupons
Wallet usage
Automatic best discount selection
Referral reward system
Wallet system (refunds, bonuses, returns)
🏗️ Architecture

Kiddora follows a monolithic Django architecture:

Frontend + Backend + Business Logic + Database (single project)

Benefits:
Faster development
Easier deployment
Centralized logic
Strong ORM integration
☁️ Deployment
AWS EC2 hosting
Nginx (reverse proxy)
Gunicorn (application server)
Cloudinary (media storage)
🗄️ Database

PostgreSQL handles:

Users & authentication
Products & categories
Orders & payments
Coupons & wallets
Inventory & returns
📌 Highlights
Complete e-commerce workflow
Secure authentication system
Admin analytics dashboard
Wallet & referral system
Advanced discount engine
AJAX-powered UX
Production deployment setup
📦 Project Status

✅ Completed (MVP + Full Feature Set)

👨‍💻 Author

Built using Django, PostgreSQL, AWS, and Cloudinary.
