from datetime import datetime
import json

import requests
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart

from aiogram.fsm.state import StatesGroup, State
from aiogram.handlers import CallbackQueryHandler
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext
from aiogram.utils.chat_action import ChatActionSender

from decouple import config

from bot import *






