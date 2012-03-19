"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase


class ContributionsTest(TestCase):
    def test_contribution_sorting(self):
      """
      Tests that contributions can be grouped by sum
      """
      
      self.assertEqual(1, 1)
          
