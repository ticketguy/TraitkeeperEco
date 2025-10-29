
# traitkeeper/admin_utils.py
from django.contrib import admin
import os
from django.conf import settings
from django.template.loader import select_template
from django.db.models import Count
from django.template.response import TemplateResponse
from django.http import HttpResponseRedirect
from nft_data.models import NFT, NFTCollection, TraitType, TraitValue 
#from analytics.models import TrendingTrait
from indexer.models import NFTEvent

class AdvancedFilterAdmin(admin.ModelAdmin):
    """
    Base admin class that adds advanced filtering capabilities based on query parameters.
    """
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        model_fields = self.model._meta.fields

        for field in model_fields:
            field_name = field.name
            field_type = field.get_internal_type()

            # Numeric fields
            if field_type in ('IntegerField', 'FloatField', 'DecimalField'):
                if f'{field_name}__gte' in request.GET:
                    try:
                        value = float(request.GET[f'{field_name}__gte']) if field_type in ('FloatField', 'DecimalField') else int(request.GET[f'{field_name}__gte'])
                        queryset = queryset.filter(**{f'{field_name}__gte': value})
                    except (ValueError, TypeError):
                        pass
                if f'{field_name}__lte' in request.GET:
                    try:
                        value = float(request.GET[f'{field_name}__lte']) if field_type in ('FloatField', 'DecimalField') else int(request.GET[f'{field_name}__lte'])
                        queryset = queryset.filter(**{f'{field_name}__lte': value})
                    except (ValueError, TypeError):
                        pass

            # Text fields
            elif field_type in ('CharField', 'TextField'):
                if f'{field_name}__icontains' in request.GET:
                    queryset = queryset.filter(**{f'{field_name}__icontains': request.GET[f'{field_name}__icontains']})

            # Boolean fields
            elif field_type == 'BooleanField':
                if field_name in request.GET:
                    if request.GET[field_name] == 'true':
                        queryset = queryset.filter(**{field_name: True})
                    elif request.GET[field_name] == 'false':
                        queryset = queryset.filter(**{field_name: False})

            # DateTime and Date fields
            elif field_type in ('DateTimeField', 'DateField'):
                if f'{field_name}__gte' in request.GET and request.GET[f'{field_name}__gte']:
                    queryset = queryset.filter(**{f'{field_name}__gte': request.GET[f'{field_name}__gte']})
                if f'{field_name}__lte' in request.GET and request.GET[f'{field_name}__lte']:
                    queryset = queryset.filter(**{f'{field_name}__lte': request.GET[f'{field_name}__lte']})

            # ForeignKey and ManyToManyField
            elif field_type in ('ForeignKey', 'ManyToManyField'):
                if f'{field_name}__pk__in' in request.GET:
                    selected_pks = request.GET.getlist(f'{field_name}__pk__in')
                    if selected_pks:
                        if field_type == 'ForeignKey':
                            queryset = queryset.filter(**{f'{field_name}__id': selected_pks[0]})
                        else:
                            # Use mint_address for NFT, address for NFTCollection
                            lookup = f'{field_name}__mint_address__in' if field.related_model == NFT else f'{field_name}__address__in'
                            queryset = queryset.filter(**{lookup: selected_pks})

        # Custom filters
        if self.model.__name__ == 'NFTCollection':
            if 'nfts_count__gte' in request.GET:
                try:
                    value = int(request.GET['nfts_count__gte'])
                    queryset = queryset.annotate(nfts_count=Count('nfts')).filter(nfts_count__gte=value)
                except (ValueError, TypeError):
                    pass
            if 'name__icontains' in request.GET:
                queryset = queryset.filter(name__icontains=request.GET['name__icontains'])

        elif self.model.__name__ == 'NFT':
            if 'name__icontains' in request.GET:
                queryset = queryset.filter(name__icontains=request.GET['name__icontains'])
            if 'events_count__gte' in request.GET:
                try:
                    value = int(request.GET['events_count__gte'])
                    queryset = queryset.annotate(events_count=Count('events')).filter(events_count__gte=value)
                except (ValueError, TypeError):
                    pass

        elif self.model.__name__ == 'TraitValue':
            if 'rarity__gte' in request.GET:
                try:
                    value = float(request.GET['rarity__gte'])
                    queryset = queryset.filter(rarity__gte=value)
                except (ValueError, TypeError):
                    pass
            if 'nfts__name__icontains' in request.GET:
                queryset = queryset.filter(nfts__name__icontains=request.GET['nfts__name__icontains'])
            if 'trait_type__collection__address__in' in request.GET:
                selected_collection_ids = request.GET.getlist('trait_type__collection__address__in')
                if selected_collection_ids:
                    queryset = queryset.filter(trait_type__collection__address__in=selected_collection_ids)
            if 'count__gte' in request.GET:
                try:
                    value = int(request.GET['count__gte'])
                    queryset = queryset.filter(count__gte=value)
                except (ValueError, TypeError):
                    pass
            if 'count__lte' in request.GET:
                try:
                    value = int(request.GET['count__lte'])
                    queryset = queryset.filter(count__lte=value)
                except (ValueError, TypeError):
                    pass
            if 'is_trending' in request.GET:
                if request.GET['is_trending'] == 'true':
                    queryset = queryset.filter(trendingtrait__isnull=False)
                elif request.GET['is_trending'] == 'false':
                    queryset = queryset.filter(trendingtrait__isnull=True)

        elif self.model.__name__ == 'TraitType':
            if 'values__nfts__mint_address__in' in request.GET:
                selected_nft_ids = request.GET.getlist('values__nfts__mint_address__in')
                if selected_nft_ids:
                    queryset = queryset.filter(values__nfts__mint_address__in=selected_nft_ids)
            if 'nfts_count__gte' in request.GET:
                try:
                    value = int(request.GET['nfts_count__gte'])
                    queryset = queryset.annotate(nfts_count=Count('values__nfts')).filter(nfts_count__gte=value)
                except (ValueError, TypeError):
                    pass
            if 'name__icontains' in request.GET:
                queryset = queryset.filter(name__icontains=request.GET['name__icontains'])
            if 'values_count__gte' in request.GET:
                try:
                    value = int(request.GET['values_count__gte'])
                    queryset = queryset.annotate(values_count=Count('values')).filter(values_count__gte=value)
                except (ValueError, TypeError):
                    pass

        elif self.model.__name__ == 'TrendingTrait':
            if 'trend_score__gte' in request.GET:
                try:
                    value = float(request.GET['trend_score__gte'])
                    queryset = queryset.filter(trend_score__gte=value)
                except (ValueError, TypeError):
                    pass
            if 'trend_score__lte' in request.GET:
                try:
                    value = float(request.GET['trend_score__lte'])
                    queryset = queryset.filter(trend_score__lte=value)
                except (ValueError, TypeError):
                    pass
            if 'trait_type__collection__address__in' in request.GET:
                selected_collection_ids = request.GET.getlist('trait_type__collection__address__in')
                if selected_collection_ids:
                    queryset = queryset.filter(trait_type__collection__address__in=selected_collection_ids)

        return queryset

    def get_filter_counts(self, request):
        """
        Calculate counts for filter options (e.g., boolean fields, related fields).
        OPTIMIZED: Replaced N+1 queries with bulk aggregation operations.
        """
        from nft_data.models import NFTCollection, NFT, TraitType, TraitValue
        from indexer.models import NFTEvent, TraitEvent
        from django.db.models import Count, Q
        
        counts = {}
        base_queryset = self.model.objects.all()
        model_fields = {field.name: field for field in self.model._meta.fields}

        # Count for boolean fields (these are already optimized)
        for field_name, field in model_fields.items():
            if field.get_internal_type() == 'BooleanField':
                counts[field_name] = {
                    'true': base_queryset.filter(**{field_name: True}).count(),
                    'false': base_queryset.filter(**{field_name: False}).count(),
                }
            elif field.get_internal_type() == 'CharField' and field.choices:
                counts[field_name] = {}
                for choice_value, _ in field.choices:
                    counts[field_name][choice_value] = base_queryset.filter(**{field_name: choice_value}).count()
            elif field.get_internal_type() in ('ForeignKey', 'ManyToManyField'):
                related_model = field.related_model
                counts[field_name] = {}
                
                # ✅ OPTIMIZED: Single aggregation query instead of N+1 loop
                if field.get_internal_type() == 'ForeignKey':
                    # Build lookup based on related model type
                    if related_model == NFTCollection:
                        lookup_field = f'{field_name}__address'
                        group_field = f'{field_name}__address'
                    elif related_model == NFT:
                        lookup_field = f'{field_name}__mint_address'
                        group_field = f'{field_name}__mint_address'
                    else:
                        # For models with standard 'id' primary key
                        lookup_field = f'{field_name}__id'
                        group_field = f'{field_name}__id'
                    
                    try:
                        # Single query to get all counts at once
                        count_data = base_queryset.values(group_field).annotate(
                            count=Count('id')
                        ).values_list(group_field, 'count')
                        
                        # Convert to dict - single operation
                        counts[field_name] = dict(count_data)
                        
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error bulk counting {field_name}: {e}")
                        counts[field_name] = {}
                        
                else:  # ManyToManyField
                    # Build lookup for M2M relationships
                    if related_model == NFT:
                        group_field = f'{field_name}__mint_address'
                    elif related_model == NFTCollection:
                        group_field = f'{field_name}__address'
                    else:
                        group_field = f'{field_name}__id'
                    
                    try:
                        # Single query for M2M counts
                        count_data = base_queryset.values(group_field).annotate(
                            count=Count('id')
                        ).values_list(group_field, 'count')
                        
                        counts[field_name] = dict(count_data)
                        
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error bulk counting M2M {field_name}: {e}")
                        counts[field_name] = {}

        # ✅ OPTIMIZED: Custom counts for specific models using bulk operations
        if self.model.__name__ == 'NFTCollection':
            # Single aggregation instead of loop
            nft_counts = base_queryset.values('nfts__mint_address').annotate(
                count=Count('id')
            ).values_list('nfts__mint_address', 'count')
            counts['nfts'] = dict(nft_counts)

        elif self.model.__name__ == 'NFT':
            # Bulk aggregation for collections
            collection_counts = base_queryset.values('collection__address').annotate(
                count=Count('id')
            ).values_list('collection__address', 'count')
            counts['collection'] = dict(collection_counts)
            
            # Bulk aggregation for trait values
            trait_value_counts = base_queryset.values('trait_values__id').annotate(
                count=Count('id')
            ).values_list('trait_values__id', 'count')
            counts['trait_values'] = dict(trait_value_counts)
            
            # Bulk aggregation for events
            event_counts = base_queryset.filter(
                events__event_type='LISTING'
            ).values('events__event_id').annotate(
                count=Count('id')
            ).values_list('events__event_id', 'count')
            counts['events'] = dict(event_counts)

        elif self.model.__name__ == 'TraitValue':
            # Bulk aggregation for collections via trait_type
            collection_counts = base_queryset.values('trait_type__collection__address').annotate(
                count=Count('id')
            ).values_list('trait_type__collection__address', 'count')
            counts['trait_type__collection'] = dict(collection_counts)
            
            # Bulk aggregation for NFTs
            nft_counts = base_queryset.values('nfts__mint_address').annotate(
                count=Count('id')
            ).values_list('nfts__mint_address', 'count')
            counts['nfts'] = dict(nft_counts)
            
            # Optimized trending counts
            counts['is_trending'] = {
                'true': base_queryset.filter(trendingtrait__isnull=False).count(),
                'false': base_queryset.filter(trendingtrait__isnull=True).count(),
            }

        elif self.model.__name__ == 'TraitType':
            # Bulk aggregation for NFTs via values
            nft_counts = base_queryset.values('values__nfts__mint_address').annotate(
                count=Count('id')
            ).values_list('values__nfts__mint_address', 'count')
            counts['values__nfts'] = dict(nft_counts)

        elif self.model.__name__ == 'TrendingTrait':
            # Bulk aggregation for collections
            collection_counts = base_queryset.values('trait_type__collection__address').annotate(
                count=Count('id')
            ).values_list('trait_type__collection__address', 'count')
            counts['trait_type__collection'] = dict(collection_counts)

        elif self.model.__name__ == 'TraitEvent':
            # Bulk aggregation for collections
            collection_counts = base_queryset.values('collection__address').annotate(
                count=Count('id')
            ).values_list('collection__address', 'count')
            counts['collection'] = dict(collection_counts)
            
            # Bulk aggregation for NFTs with null handling
            nft_counts = base_queryset.values('nft__mint_address').annotate(
                count=Count('id')
            ).values_list('nft__mint_address', 'count')
            counts['nft'] = dict(nft_counts)
            
            # Add null count for NFTs
            counts['nft']['null'] = base_queryset.filter(nft__isnull=True).count()

        return counts

    def changelist_view(self, request, extra_context=None):
        """
        OPTIMIZED: Fixed N+1 queries in related object fetching.
        """
        if request.method == 'POST' and 'action' in request.POST:
            return super().changelist_view(request, extra_context)

        model_fields = self.model._meta.fields
        fields_info = []
        selected_related_pks = {}
        
        # ✅ OPTIMIZATION: Group related models to avoid duplicate queries
        related_models_to_fetch = {}
        
        # First pass: identify which related models we need
        for field in model_fields:
            if field.get_internal_type() in ('ForeignKey', 'ManyToManyField'):
                related_model = field.related_model
                if related_model not in related_models_to_fetch:
                    related_models_to_fetch[related_model] = []
                related_models_to_fetch[related_model].append(field)
        
        # ✅ OPTIMIZATION: Fetch related objects with optimized queries
        related_objects_cache = {}
        
        for related_model, fields in related_models_to_fetch.items():
            try:
                # Optimize queries based on model type
                if related_model.__name__ == 'NFTCollection':
                    # Optimize for NFTCollection with related data that might be in __str__
                    queryset = related_model.objects.all().select_related().prefetch_related('nfts')
                    
                elif related_model.__name__ == 'NFT':
                    # Optimize for NFT with collection and traits
                    queryset = related_model.objects.all().select_related('collection').prefetch_related('trait_values__trait_type')
                    
                elif related_model.__name__ == 'TraitType':
                    # Optimize for TraitType with collection
                    queryset = related_model.objects.all().select_related('collection').prefetch_related('values')
                    
                elif related_model.__name__ == 'TraitValue':
                    # Optimize for TraitValue with trait_type and collection
                    queryset = related_model.objects.all().select_related('trait_type__collection').prefetch_related('nfts')
                    
                elif related_model.__name__ == 'NFTEvent':
                    # Optimize for NFTEvent with collection
                    queryset = related_model.objects.all().select_related('collection')
                    
                elif related_model.__name__ == 'CollectionMarketStats':
                    # Optimize for CollectionMarketStats with collection
                    queryset = related_model.objects.all().select_related('collection')
                    
                else:
                    # Default optimization for other models
                    queryset = related_model.objects.all().select_related()
                
                # ✅ SINGLE QUERY: Fetch all objects for this model at once
                related_objects_cache[related_model] = list(queryset)
                
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error fetching optimized {related_model.__name__}: {e}")
                # Fallback to basic query
                related_objects_cache[related_model] = list(related_model.objects.all())

        # Second pass: build fields_info using cached data
        for field in model_fields:
            field_info = {
                'name': field.name,
                'verbose_name': field.verbose_name,
                'type': field.get_internal_type(),
                'choices': field.choices if hasattr(field, 'choices') else None,
            }
            
            if field.get_internal_type() in ('ForeignKey', 'ManyToManyField'):
                related_model = field.related_model
                
                # ✅ USE CACHED DATA: No additional queries
                related_objects = related_objects_cache.get(related_model, [])
                
                # Build the (pk, str) tuples - str(obj) uses prefetched data
                field_info['related_objects'] = [(obj.pk, str(obj)) for obj in related_objects]
                
                # Handle selected PKs
                selected_pks = request.GET.getlist(f'{field.name}__pk__in')
                selected_related_pks[field.name] = set(str(pk) for pk in selected_pks)
                
            fields_info.append(field_info)

        # ✅ OPTIMIZATION: Handle model-specific selected PKs more efficiently
        if self.model.__name__ == 'TraitValue':
            selected_collection_ids = request.GET.getlist('trait_type__collection__address__in')
            selected_related_pks['trait_type__collection'] = set(str(pk) for pk in selected_collection_ids)

        elif self.model.__name__ == 'TraitType':
            selected_nft_ids = request.GET.getlist('values__nfts__mint_address__in')
            selected_related_pks['values__nfts'] = set(str(pk) for pk in selected_nft_ids)

        elif self.model.__name__ == 'TrendingTrait':
            selected_collection_ids = request.GET.getlist('trait_type__collection__address__in')
            selected_related_pks['trait_type__collection'] = set(str(pk) for pk in selected_collection_ids)

        # Call parent method
        response = super().changelist_view(request, extra_context)
        
        if isinstance(response, TemplateResponse):
            cl = response.context_data['cl']
            
            # ✅ OPTIMIZATION: Efficient pagination calculation
            pagination_range = []
            if cl.paginator:
                current_page = cl.page_num
                num_pages = cl.paginator.num_pages
                start_page = max(1, current_page - 2)
                end_page = min(num_pages, current_page + 2)
                if start_page == 1:
                    end_page = min(num_pages, start_page + 4)
                if end_page == num_pages:
                    start_page = max(1, end_page - 4)
                pagination_range = range(start_page, end_page + 1)

            # Build context with optimized data
            extra_context = extra_context or {}
            extra_context.update({
                'model_fields': fields_info,
                'pagination_range': pagination_range,
                'filter_counts': self.get_filter_counts(request),  # Uses our optimized method
                'selected_related_pks': selected_related_pks
            })
            
            response.context_data.update(extra_context)

        return response

    def get_changelist_template(self):
        return "admin/change_list.html"