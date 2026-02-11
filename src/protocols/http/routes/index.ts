import _ from "radash";
import { Router } from "express";
import axios from 'axios';

const router = Router();

router.get('/check', (req, res) => res.sendStatus(200));


export default router;
