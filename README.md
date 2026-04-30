# 👶 Kiddora – Kids E-Commerce Platform

> A full-featured Django-based e-commerce web application for kids' clothing (Newborn to 15 years), built for production with secure authentication, seamless checkout, payment integration, and scalable cloud deployment.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Features](#features)
  - [Admin Module](#admin-module)
  - [User Module](#user-module)
- [Core Business Logic](#core-business-logic)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Database](#database)
- [Project Status](#project-status)
- [Author](#author)

---

## Overview

Kiddora is a production-ready monolithic Django e-commerce platform that integrates frontend and backend within a single project. It delivers a complete online shopping ecosystem for children's clothing, featuring a powerful admin dashboard, smooth customer experience, wallet and referral systems, and full payment gateway integration.

---

## Tech Stack

### 🖥️ Backend
- **Python** & **Django**
- **Django ORM**
- **PostgreSQL**

### 🎨 Frontend
- **HTML5**, **CSS3**, **Bootstrap**
- **JavaScript** & **AJAX**

### 🔐 Authentication & Security
- Email OTP Verification
- Social Login (SSO)
- Forgot Password Flow
- Secure Session Handling
- CSRF Protection
- Role-Based Access Control

### ☁️ Storage & Deployment
- **Cloudinary** – Media & Static Files
- **AWS EC2** – Hosting
- **Gunicorn** – WSGI Server
- **Nginx** – Reverse Proxy & Static Serving

### 💳 Payment Integration
- PayPal Sandbox
- Cash on Delivery (COD)

---

## Features

### 🛠️ Admin Module

A powerful dashboard for complete business control.

**User Management**
- Secure admin authentication with role-based access
- Block / Unblock users with confirmation prompts
- Backend search, pagination, and latest-first sorting

**Category Management**
- Add, Edit, and Soft Delete categories
- Search, filter, and paginated listings

**Product Management**
- Add, Edit, and Soft Delete products
- Multiple image upload with cropping and resizing
- Backend search and pagination

**Orders & Inventory**
- Order tracking dashboard with status management
- Return and cancellation handling
- Automated stock synchronization

**Offers & Coupons**
- Coupon creation with single-use enforcement
- Dynamic discount calculation with maximum discount logic
- Referral reward system with wallet credit integration
- Sales analytics dashboard

---

### 🛍️ User Module

**Authentication**
- Secure signup & login
- OTP-based email verification with resend and countdown timer
- Social login (SSO) and forgot password flow

**Profile Management**
- View and edit profile with image upload
- OTP/token-based email change verification
- Password change and address management (Add / Edit / Delete)

**Product Discovery**
- Browse products with advanced search, multi-filter support, and sorting options

**Wishlist & Cart**
- AJAX-powered wishlist and cart management
- Real-time quantity updates, stock validation, and out-of-stock prevention

**Checkout & Payments**
- Address selection with order summary and breakdown
- Coupon and wallet application at checkout
- PayPal and COD payment with success/failure handling

**Order Lifecycle**
- Order history, tracking, and detailed order view
- Invoice download
- Cancel / Return with reason capture
- Refund processing via wallet with stock restoration

---

## Core Business Logic

### 💰 Discount Engine
Kiddora intelligently calculates the best available discount using:
- Product-level offers
- Category-level offers
- Coupons
- Referral bonuses
- Wallet credits

The engine automatically applies the maximum valid discount while preserving all business rules.

### 👛 Wallet System
Users earn wallet credits from returns, refunds, referral rewards, and promotional credits. Credits can be applied at checkout.

### 🔁 Referral System
Invite-based referral system that rewards users with wallet credits upon successful signups via their referral link.

### 🔎 Search & Pagination
Implemented across Users, Categories, Products, and Orders with backend search, clear functionality, efficient pagination, and sorted listings.

### 🗑️ Soft Delete Strategy
Applied to categories, products, and key business entities — supports data recovery, preserves reporting integrity, and prevents accidental permanent deletion.

---

## Architecture

Kiddora follows a **Monolithic Django Architecture**, with Frontend, Backend, Business Logic, and Database unified in a single system.

**Advantages:**
- Simplified deployment
- Centralized logic and easier maintenance
- Faster development cycle
- Strong Django ORM integration

---

## Deployment

Deployed on **AWS EC2** using a production-ready stack:

```
AWS EC2
   ↓
Nginx  (Reverse Proxy & Static Serving)
   ↓
Gunicorn  (WSGI Server)
   ↓
Django  (Application)
   ↓
PostgreSQL  (Database)
   ↓
Cloudinary CDN  (Media & Static Files)
```

- Production-ready hosting with secure environment configuration
- Static and media offloading to Cloudinary
- Scalable and maintainable infrastructure

---

## Database

Uses **PostgreSQL** for robust, ACID-compliant data handling.

**Key Entities:**
- Users
- Products & Categories
- Orders
- Coupons
- Wallet & Referrals
- Inventory
- Returns & Refunds

---

## Project Highlights

| Feature | Status |
|---|---|
| Secure Authentication System | ✅ |
| Advanced Admin Dashboard | ✅ |
| Payment Gateway Integration (PayPal + COD) | ✅ |
| Wallet + Referral System | ✅ |
| Coupons & Discount Engine | ✅ |
| Inventory Synchronization | ✅ |
| Invoice Generation | ✅ |
| Return & Refund Workflows | ✅ |
| AJAX-Powered UX | ✅ |
| Cloud Deployment (AWS EC2 + Cloudinary) | ✅ |

---

## Project Status

**✅ Completed**

Kiddora is fully developed with a complete Admin Module, Customer Module, E-commerce Engine, Payment System, and Analytics Dashboard. The platform is ready for production scaling and future enhancements.

---

## Author

Developed with Django • PostgreSQL • Cloudinary • AWS ☁️
