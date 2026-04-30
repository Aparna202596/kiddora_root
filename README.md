👶 Kiddora – Kids E-Commerce Platform 👕🛍️

Kiddora is a full-featured monolithic Django-based e-commerce web application designed for kids’ clothing (Newborn to 15 years). It is a production-ready online shopping platform with secure authentication, robust admin controls, seamless checkout experience, payment integration, offer management, and scalable deployment architecture.

The platform integrates both frontend and backend within a single Django project, delivering a complete e-commerce ecosystem with efficient administration tools and a smooth customer shopping experience.

🚀 Tech Stack
🖥️ Backend
Python
Django
Django ORM
PostgreSQL
🎨 Frontend
HTML5
CSS3
Bootstrap
JavaScript
AJAX
🔐 Authentication & Security
Email OTP Verification
Social Login (Single Sign-On)
Forgot Password Flow
Secure Session Handling
CSRF Protection
Role-Based Access Control
☁️ Storage & Deployment
Cloudinary (Media & Static Files)
AWS EC2 (Hosting)
Gunicorn (WSGI Server)
Nginx (Reverse Proxy & Static Serving)
💳 Payment Integration
PayPal Sandbox
Cash on Delivery (COD)
✨ Key Features
🛠️ 1. Admin Module

A powerful admin dashboard for complete business control.

👤 User Management
Secure admin authentication
Role-based dashboard access
Block / Unblock users
Confirmation prompts for critical actions
Backend search with clear functionality
Pagination for large datasets
Latest-first sorting
📦 Category Management
Add / Edit / Soft Delete categories
Search & filter categories
Pagination support
Optimized sorting
🧸 Product Management
Add / Edit / Soft Delete products
Multiple image upload
Image cropping & resizing
Product optimization for UI
Backend search & pagination
📊 Orders & Inventory
Order tracking dashboard
Order status management
Return & cancellation handling
Stock synchronization
Automated inventory updates
🎟️ Offers & Coupons
Coupon creation and control
Single-use coupon enforcement
Dynamic discount calculation
Maximum discount logic engine
Referral reward system
Wallet credit integration
Sales analytics dashboard
🛍️ 2. User Module
🔐 Authentication System
Secure signup & login
OTP-based verification with timer
Resend OTP functionality
Social login (SSO)
Forgot password flow
👤 Profile Management
View & edit profile
Profile image upload
Email change verification (OTP/token)
Password change
Address management (Add/Edit/Delete)
🔍 Product Discovery
Product browsing
Advanced search
Multi-filter support
Sorting options
Optimized UX browsing flow
❤️ Wishlist & Cart
Wishlist
Add / Remove items
AJAX-powered updates
Cart
Add / Remove items
Quantity increment/decrement
Stock validation
Out-of-stock prevention
Real-time updates via AJAX
💳 Checkout & Payments
Address selection
Order summary with breakdown
Coupon application
Wallet usage
PayPal payment integration
COD support
Payment success/failure handling
📦 Order Lifecycle
Order history & tracking
Detailed order view
Search orders
Invoice download
Cancel / Return orders
Return reason capture
Refund processing
Wallet-based refunds
Stock restoration logic
🧠 Core Business Logic
💰 Discount Engine

Kiddora intelligently calculates best discounts using:

Product offers
Category offers
Coupons
Referral bonuses
Wallet credits

✔ Automatically applies the maximum valid discount while preserving business rules.

👛 Wallet System

Users earn and use wallet credits from:

Returns & refunds
Referral rewards
Promotional credits

Wallet can be used during checkout.

🔁 Referral System
Invite-based rewards
Referral bonus credits
Wallet integration
🔎 Search & Pagination

Implemented across:

Users
Categories
Products
Orders

Features:

Backend search
Clear search functionality
Efficient pagination
Sorted listings
🗑️ Soft Delete Strategy

Applied to:

Categories
Products
Key business entities

Benefits:

Data recovery support
Reporting integrity
Prevents accidental permanent deletion
🏗️ Architecture

Kiddora follows a Monolithic Django Architecture:

Frontend + Backend + Business Logic + Database in a unified system

✔ Advantages
Simplified deployment
Centralized logic
Faster development cycle
Easier maintenance
Strong Django ORM integration
☁️ Deployment

Deployed on AWS EC2 using production-ready stack:

AWS EC2
   ↓
Nginx
   ↓
Gunicorn
   ↓
Django
   ↓
PostgreSQL
   ↓
Cloudinary CDN
✔ Features
Production-ready hosting
Secure environment configuration
Static/media offloading to Cloudinary
Scalable infrastructure
🗄️ Database

Uses PostgreSQL for robust data handling:

Entities:

Users
Products
Categories
Orders
Coupons
Wallet
Referrals
Inventory
Returns & Refunds
✔ Benefits
ACID compliance
High performance
Scalability
Reliability
🌟 Highlights

✔ Production-ready full-stack project
✔ Secure authentication system
✔ Advanced admin dashboard
✔ Payment gateway integration
✔ Wallet + referral system
✔ Coupons & discount engine
✔ Inventory synchronization
✔ Invoice generation system
✔ Return & refund workflows
✔ AJAX-powered user experience
✔ Cloud deployment (AWS EC2 + Cloudinary)

📌 Project Status

✔ Completed

Kiddora is fully developed with complete:

Admin Module
Customer Module
E-commerce Engine
Payment System
Analytics Dashboard

Ready for production scaling and future enhancements.

👨‍💻 Author

Developed using:
Django • PostgreSQL • Cloudinary • AWS ☁️
