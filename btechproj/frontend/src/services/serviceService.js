import api from './api';
import { servicesHealthData, dashboardStats } from '../data/mockData';

/**
 * Fetch list of monitored services and health telemetry
 * Endpoint: GET /services
 */
export const getServices = async () => {
  const response = await api.get('/services');
  const servicesList = response.data.services || response.data;
  return { data: servicesList, isMock: false };
};

/**
 * Fetch high-level dashboard overview metrics
 * Endpoint: GET /dashboard/overview
 */
export const getDashboardOverview = async () => {
  const response = await api.get('/dashboard/overview');
  return { data: response.data, isMock: false };
};

/**
 * Alias for backward compatibility
 */
export const getDashboardStats = getDashboardOverview;

/**
 * Fetch real live cluster telemetry & alert rules for Monitoring Page
 * Endpoint: GET /monitoring
 */
export const getMonitoringData = async () => {
  const response = await api.get('/monitoring');
  return { data: response.data, isMock: false };
};
