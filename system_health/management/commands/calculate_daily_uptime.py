#!/usr/bin/env python
"""
Management command to calculate daily uptime statistics.
Run this once per day (via cron or scheduled task) to populate ServiceUptime records.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import datetime, timedelta
from system_health.models import ServiceHealthCheck, ServiceUptime
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Calculate and store daily uptime statistics for all services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Calculate uptime for specific date (YYYY-MM-DD). Default: yesterday'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Number of days to calculate (working backwards from date). Default: 1'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recalculate even if data already exists'
        )

    def handle(self, *args, **options):
        # Determine date range
        if options['date']:
            end_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
        else:
            # Default to yesterday (don't calculate today until it's complete)
            end_date = timezone.now().date() - timedelta(days=1)

        days_count = options['days']
        force = options['force']

        self.stdout.write(self.style.SUCCESS(
            f'Calculating uptime for {days_count} day(s) ending {end_date}'
        ))

        # Calculate for each day
        total_calculated = 0
        total_skipped = 0
        total_errors = 0

        for i in range(days_count):
            calc_date = end_date - timedelta(days=i)

            try:
                calculated, skipped = self.calculate_day_uptime(calc_date, force)
                total_calculated += calculated
                total_skipped += skipped

                if calculated > 0:
                    self.stdout.write(
                        f'  {calc_date}: Calculated {calculated} services'
                    )
                elif skipped > 0:
                    self.stdout.write(
                        self.style.WARNING(f'  {calc_date}: Skipped {skipped} existing records')
                    )

            except Exception as e:
                total_errors += 1
                self.stdout.write(
                    self.style.ERROR(f'  {calc_date}: Error - {str(e)}')
                )
                logger.exception(f'Error calculating uptime for {calc_date}')

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'\nSummary:\n'
            f'  Calculated: {total_calculated}\n'
            f'  Skipped: {total_skipped}\n'
            f'  Errors: {total_errors}'
        ))

    def calculate_day_uptime(self, date, force=False):
        """Calculate uptime for all services on a specific date."""
        day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        day_end = timezone.make_aware(datetime.combine(date, datetime.max.time()))

        # Get all unique services that have health checks
        services = ServiceHealthCheck.SERVICE_CHOICES

        calculated = 0
        skipped = 0

        for service_key, service_name in services:
            # Check if already calculated (unless force=True)
            if not force:
                exists = ServiceUptime.objects.filter(
                    service_name=service_key,
                    date=date
                ).exists()

                if exists:
                    skipped += 1
                    continue

            # Get all health checks for this service on this day
            checks = ServiceHealthCheck.objects.filter(
                service_name=service_key,
                checked_at__gte=day_start,
                checked_at__lte=day_end
            )

            total_checks = checks.count()

            if total_checks == 0:
                # No data for this day - create record with null/zero values
                ServiceUptime.objects.update_or_create(
                    service_name=service_key,
                    date=date,
                    defaults={
                        'uptime_percentage': 0,
                        'total_checks': 0,
                        'successful_checks': 0,
                        'failed_checks': 0,
                        'avg_response_time_ms': None,
                        'downtime_minutes': 0,
                        'incidents_count': 0,
                    }
                )
                calculated += 1
                continue

            # Calculate statistics
            successful_checks = checks.filter(status='healthy').count()
            failed_checks = total_checks - successful_checks
            uptime_percentage = (successful_checks / total_checks * 100) if total_checks > 0 else 0

            # Calculate average response time
            avg_response = checks.aggregate(
                avg_time=Avg('response_time_ms')
            )['avg_time']

            # Calculate downtime
            downtime_minutes = self.calculate_downtime(checks, day_start, day_end)

            # Calculate incidents (consecutive failures)
            incidents_count = self.calculate_incidents(checks.order_by('checked_at'))

            # Create or update the uptime record
            ServiceUptime.objects.update_or_create(
                service_name=service_key,
                date=date,
                defaults={
                    'uptime_percentage': round(uptime_percentage, 2),
                    'total_checks': total_checks,
                    'successful_checks': successful_checks,
                    'failed_checks': failed_checks,
                    'avg_response_time_ms': round(avg_response, 2) if avg_response else None,
                    'downtime_minutes': round(downtime_minutes, 2),
                    'incidents_count': incidents_count,
                    'metadata': {
                        'calculated_at': timezone.now().isoformat(),
                        'day_start': day_start.isoformat(),
                        'day_end': day_end.isoformat(),
                    }
                }
            )

            calculated += 1

        return calculated, skipped

    def calculate_downtime(self, checks, day_start, day_end):
        """
        Calculate total downtime in minutes.
        Assumes checks are spaced every 5 minutes (default health check interval).
        """
        failed_checks = checks.filter(status__in=['unhealthy', 'error']).count()

        # Assume 5-minute intervals (adjust based on your actual check frequency)
        check_interval_minutes = 5
        downtime_minutes = failed_checks * check_interval_minutes

        return downtime_minutes

    def calculate_incidents(self, ordered_checks):
        """
        Calculate number of distinct downtime incidents.
        An incident is a sequence of consecutive failures.
        """
        incidents = 0
        in_incident = False

        for check in ordered_checks:
            is_healthy = check.status == 'healthy'

            if not is_healthy and not in_incident:
                # Start of new incident
                incidents += 1
                in_incident = True
            elif is_healthy and in_incident:
                # End of incident
                in_incident = False

        return incidents
